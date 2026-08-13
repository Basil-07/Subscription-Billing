import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models
from app.core.config import settings

def verify_webhook_signature(raw_body: bytes, signature: str, timestamp_str: str) -> bool:
    """
    Validates the webhook timestamp and cryptographic signature using HMAC-SHA256.
    """
    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False

    # 1. Replay window validation (5 minutes)
    now = int(datetime.now(timezone.utc).timestamp())
    if abs(now - timestamp) > 300:
        return False

    # 2. HMAC-SHA256 signature verification
    signed_payload = f"{timestamp_str}.{raw_body.decode()}"
    expected_signature = hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature)

def process_webhook_event(db: Session, payload: dict) -> tuple[str, int]:
    """
    Safely processes an authenticated webhook event inside a transaction.
    Handles duplicates, late payments, out-of-order deliveries, and creates reconciliation records.
    """
    gateway_event_id = payload.get("gateway_event_id")
    event_type = payload.get("event_type")
    merchant_reference = payload.get("merchant_reference")
    gateway_charge_id = payload.get("gateway_charge_id")
    amount_cents = payload.get("amount_cents")
    event_timestamp_str = payload.get("event_timestamp")

    if not all([gateway_event_id, event_type, merchant_reference, gateway_charge_id, amount_cents, event_timestamp_str]):
        return "Malformed payload schema", 400

    try:
        event_timestamp = datetime.fromisoformat(event_timestamp_str.replace("Z", "+00:00"))
    except ValueError:
        return "Invalid event timestamp format", 400

    # 1. Check database level event-id uniqueness to prevent duplicate webhook delivery
    existing_event = db.query(models.WebhookEvent).filter(
        models.WebhookEvent.gateway_event_id == gateway_event_id
    ).first()

    if existing_event:
        return "IGNORED_DUPLICATE", 200

    # Insert WebhookEvent record in a new state
    new_event = models.WebhookEvent(
        id=uuid.uuid4(),
        gateway_event_id=gateway_event_id,
        event_type=event_type,
        merchant_reference=merchant_reference,
        gateway_charge_id=gateway_charge_id,
        event_timestamp=event_timestamp,
        payload=payload,
        processing_status="RECEIVED"
    )
    db.add(new_event)
    db.flush() # flush to generate id and verify unique constraints without committing yet

    # 2. Find associated payment by merchant_reference or gateway_charge_id
    payment = db.query(models.Payment).filter(
        (models.Payment.merchant_reference == merchant_reference) |
        (models.Payment.gateway_charge_id == gateway_charge_id)
    ).first()

    if not payment:
        new_event.processing_status = "FAILED"
        new_event.processing_result = "Unknown merchant_reference or gateway_charge_id"
        new_event.processed_at = datetime.now(timezone.utc)
        db.commit()
        return "Unknown payment reference", 400

    try:
        # 3. SELECT FOR UPDATE on payment, plan_change and subscription to serialize updates
        locked_payment = db.query(models.Payment).filter(
            models.Payment.id == payment.id
        ).with_for_update().first()

        locked_pc = db.query(models.PlanChange).filter(
            models.PlanChange.id == locked_payment.plan_change_id
        ).with_for_update().first()

        locked_sub = db.query(models.Subscription).filter(
            models.Subscription.id == locked_pc.subscription_id
        ).with_for_update().first()

        # 4. Evaluate payment state: ignore if payment is already succeeded
        if locked_payment.status == "SUCCEEDED":
            new_event.processing_status = "IGNORED"
            new_event.processing_result = "Ignored: payment is already succeeded"
            new_event.processed_at = datetime.now(timezone.utc)
            db.commit()
            return "IGNORED_STALE", 200

        # Process payment state transitions
        if event_type == "SUCCEEDED":
            locked_payment.status = "SUCCEEDED"
            locked_payment.gateway_charge_id = gateway_charge_id

            if locked_pc.status == "AWAITING_PAYMENT":
                # Defensive check: if subscription was cancelled in the meantime
                # (and this is not a reactivation request, which has from_plan_id = None),
                # do NOT activate/change plan. Reconcile instead!
                if locked_sub.status == "CANCELLED" and locked_pc.from_plan_id is not None:
                    recon_ledger = models.LedgerEntry(
                        id=uuid.uuid4(),
                        customer_id=locked_sub.customer_id,
                        plan_change_id=locked_pc.id,
                        payment_id=locked_payment.id,
                        type="CHARGE",
                        amount_cents=locked_payment.amount_cents,
                        status="PENDING",
                        is_reconciliation=True
                    )
                    db.add(recon_ledger)
                    db.flush()

                    recon_record = models.ReconciliationRecord(
                        id=uuid.uuid4(),
                        payment_id=locked_payment.id,
                        plan_change_id=locked_pc.id,
                        ledger_entry_id=recon_ledger.id,
                        reason="Payment succeeded after subscription was cancelled",
                        status="PENDING"
                    )
                    db.add(recon_record)

                    new_event.processing_status = "PROCESSED"
                    new_event.processing_result = "Applied: Subscription remains cancelled. Payment flagged for reconciliation."
                else:
                    # Regular confirmation flow
                    locked_pc.status = "CONFIRMED"
                    
                    # Post the ledger entry
                    ledger_entry = db.query(models.LedgerEntry).filter(
                        models.LedgerEntry.plan_change_id == locked_pc.id,
                        models.LedgerEntry.status == "PENDING"
                    ).first()
                    if ledger_entry:
                        ledger_entry.status = "POSTED"
                        ledger_entry.posted_at = datetime.now(timezone.utc)

                    # Update the subscription plan
                    if locked_sub.status == "CANCELLED":
                        # Reactivation: reset the billing cycle to start from payment confirmation
                        locked_sub.cycle_start = datetime.now(timezone.utc)
                        locked_sub.cycle_end = locked_sub.cycle_start + timedelta(days=30)

                    locked_sub.plan_id = locked_pc.to_plan_id
                    if locked_pc.to_plan_id is None:
                        locked_sub.status = "CANCELLED"
                    else:
                        locked_sub.status = "ACTIVE"
                    locked_sub.version += 1

                    new_event.processing_status = "PROCESSED"
                    new_event.processing_result = "Applied: Subscription updated and ledger posted."

            elif locked_pc.status in ["SUPERSEDED", "FAILED"]:
                # Late payment success for a superseded or failed plan change!
                # 1. DO NOT change the active subscription plan.
                # 2. Record reconciliation ledger entry: CHARGE, PENDING, is_reconciliation=True
                recon_ledger = models.LedgerEntry(
                    id=uuid.uuid4(),
                    customer_id=locked_sub.customer_id,
                    plan_change_id=locked_pc.id,
                    payment_id=locked_payment.id,
                    type="CHARGE",
                    amount_cents=locked_payment.amount_cents,
                    status="PENDING",
                    is_reconciliation=True
                )
                db.add(recon_ledger)
                db.flush()

                # 3. Create ReconciliationRecord
                recon_record = models.ReconciliationRecord(
                    id=uuid.uuid4(),
                    payment_id=locked_payment.id,
                    plan_change_id=locked_pc.id,
                    ledger_entry_id=recon_ledger.id,
                    reason=f"Late success webhook for {locked_pc.status.lower()} plan change",
                    status="PENDING"
                )
                db.add(recon_record)

                new_event.processing_status = "PROCESSED"
                new_event.processing_result = f"Applied: Payment recorded as SUCCEEDED, flagged for reconciliation due to {locked_pc.status.lower()} change."

        elif event_type == "FAILED":
            # If the payment was already failed, this is a duplicate failure, so we ignore it.
            if locked_payment.status == "FAILED":
                new_event.processing_status = "IGNORED"
                new_event.processing_result = "Ignored: payment is already failed"
                new_event.processed_at = datetime.now(timezone.utc)
                db.commit()
                return "IGNORED_STALE", 200

            locked_payment.status = "FAILED"
            locked_payment.gateway_charge_id = gateway_charge_id

            if locked_pc.status == "AWAITING_PAYMENT":
                locked_pc.status = "FAILED"
                
                # Reverse ledger entry
                ledger_entry = db.query(models.LedgerEntry).filter(
                    models.LedgerEntry.plan_change_id == locked_pc.id,
                    models.LedgerEntry.status == "PENDING"
                ).first()
                if ledger_entry:
                    ledger_entry.status = "REVERSED"

                new_event.processing_status = "PROCESSED"
                new_event.processing_result = "Applied: Payment failed, plan change failed."

            elif locked_pc.status == "SUPERSEDED":
                # Stale failure on a superseded plan change. Nothing to reverse because it was already reversed when superseded.
                new_event.processing_status = "PROCESSED"
                new_event.processing_result = "Applied: Stale payment failure acknowledged, no action required."

        new_event.processed_at = datetime.now(timezone.utc)
        db.commit()
        return "APPLIED", 200

    except Exception as e:
        db.rollback()
        # Mark webhook event as failed
        db.begin()
        failed_event = db.query(models.WebhookEvent).filter(models.WebhookEvent.id == new_event.id).first()
        if failed_event:
            failed_event.processing_status = "FAILED"
            failed_event.processing_result = f"Exception: {str(e)}"
            failed_event.processed_at = datetime.now(timezone.utc)
            db.commit()
        return f"Processing failed: {str(e)}", 500
