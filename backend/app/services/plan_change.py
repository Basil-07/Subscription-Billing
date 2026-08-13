import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app import models
from app.services.proration import calculate_proration

class ConflictError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)

class NotFoundError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=404, detail=detail)

class BadRequestError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)

def create_plan_change(
    db: Session,
    subscription_id: str,
    to_plan_id: str | None,
    idempotency_key: str,
    requested_at: datetime | None = None
) -> models.PlanChange:
    # Convert string UUIDs to UUID objects for SQLite/PostgreSQL compatibility
    sub_uuid = uuid.UUID(subscription_id) if isinstance(subscription_id, str) else subscription_id
    to_plan_uuid = uuid.UUID(to_plan_id) if isinstance(to_plan_id, str) else to_plan_id

    # 1. Generate canonical request fingerprint
    canonical_str = f"to_plan_id:{to_plan_id}"
    request_hash = hashlib.sha256(canonical_str.encode()).hexdigest()

    # 2. Check for duplicate idempotency key (pre-transaction check for speed/idempotency)
    existing_change = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == sub_uuid,
        models.PlanChange.idempotency_key == idempotency_key
    ).first()

    if existing_change:
        if existing_change.request_hash == request_hash:
            return existing_change
        else:
            raise ConflictError("Idempotency-key reuse with different request")

    if requested_at is None:
        requested_at = datetime.now(timezone.utc)

    # Convert to timezone aware if native
    if requested_at.tzinfo is None:
        requested_at = requested_at.replace(tzinfo=timezone.utc)

    # 3. Enter database transaction
    try:
        # 4. Pessimistic locking: SELECT ... FOR UPDATE
        sub = db.query(models.Subscription).filter(
            models.Subscription.id == sub_uuid
        ).with_for_update().first()

        if not sub:
            raise NotFoundError("Subscription not found")

        # Double check idempotency under row lock
        lock_checked_change = db.query(models.PlanChange).filter(
            models.PlanChange.subscription_id == sub_uuid,
            models.PlanChange.idempotency_key == idempotency_key
        ).first()
        if lock_checked_change:
            if lock_checked_change.request_hash == request_hash:
                return lock_checked_change
            else:
                raise ConflictError("Idempotency-key reuse with different request")

        # Handle cancellation checks
        if to_plan_uuid is None:
            if sub.status == "CANCELLED":
                # Duplicate cancellation is a safe no-op
                # Create a dummy plan change that is confirmed immediately with 0 cents
                dummy_change = models.PlanChange(
                    id=uuid.uuid4(),
                    subscription_id=sub_uuid,
                    from_plan_id=sub.plan_id or uuid.UUID("b0000000-0000-4000-8000-000000000000"),
                    to_plan_id=None,
                    credit_cents=0,
                    charge_cents=0,
                    net_cents=0,
                    status="CONFIRMED",
                    requested_at=requested_at,
                    effective_at=requested_at,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash
                )
                db.add(dummy_change)
                db.commit()
                return dummy_change
        else:
            # Check target plan exists
            target_plan = db.query(models.Plan).filter(models.Plan.id == to_plan_uuid).first()
            if not target_plan:
                raise BadRequestError("Target plan not found")

            # Check if active subscription already has this plan
            if sub.status == "ACTIVE" and str(sub.plan_id) == str(to_plan_uuid):
                # Same plan requested is a no-op
                dummy_change = models.PlanChange(
                    id=uuid.uuid4(),
                    subscription_id=sub_uuid,
                    from_plan_id=sub.plan_id,
                    to_plan_id=to_plan_uuid,
                    credit_cents=0,
                    charge_cents=0,
                    net_cents=0,
                    status="CONFIRMED",
                    requested_at=requested_at,
                    effective_at=requested_at,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash
                )
                db.add(dummy_change)
                db.commit()
                return dummy_change

            if sub.status == "CANCELLED":
                # Reactivation: set new cycle start and end dates immediately
                # so proration calculation computes full charge for a 30-day period.
                sub.cycle_start = requested_at
                sub.cycle_end = requested_at + timedelta(days=30)

        # 5. Supersede existing AWAITING_PAYMENT plan change
        pending_changes = db.query(models.PlanChange).filter(
            models.PlanChange.subscription_id == sub_uuid,
            models.PlanChange.status == "AWAITING_PAYMENT"
        ).all()

        for pc in pending_changes:
            pc.status = "SUPERSEDED"
            # Reverse its corresponding PENDING ledger entry
            pending_ledgers = db.query(models.LedgerEntry).filter(
                models.LedgerEntry.plan_change_id == pc.id,
                models.LedgerEntry.status == "PENDING"
            ).all()
            for le in pending_ledgers:
                le.status = "REVERSED"

        # 6. Capture effective_at (authoritative)
        effective_at = datetime.now(timezone.utc)

        # 7. Compute proration against CURRENT CONFIRMED plan
        old_plan = db.query(models.Plan).filter(models.Plan.id == sub.plan_id).first()
        old_price = old_plan.price_cents if old_plan else 0
        new_price = target_plan.price_cents if to_plan_uuid is not None else 0

        if sub.plan_id is None:
            credit_cents = 0
            charge_cents = new_price
            net_cents = new_price
        else:
            credit_cents, charge_cents, net_cents = calculate_proration(
                old_plan_price=old_price,
                new_plan_price=new_price,
                cycle_start=sub.cycle_start,
                cycle_end=sub.cycle_end,
                effective_at=effective_at
            )

        plan_change_id = uuid.uuid4()
        new_change = models.PlanChange(
            id=plan_change_id,
            subscription_id=sub_uuid,
            from_plan_id=sub.plan_id,
            to_plan_id=to_plan_uuid,
            credit_cents=credit_cents,
            charge_cents=charge_cents,
            net_cents=net_cents,
            status="AWAITING_PAYMENT" if net_cents > 0 else "CONFIRMED",
            requested_at=requested_at,
            effective_at=effective_at,
            idempotency_key=idempotency_key,
            request_hash=request_hash
        )
        db.add(new_change)

        # 8. Handle financial side effects based on net_cents
        if net_cents <= 0:
            # Downgrade/Cancellation/Zero-price changes are confirmed immediately
            sub.plan_id = to_plan_uuid
            if to_plan_uuid is None:
                sub.status = "CANCELLED"
            sub.version += 1

            if net_cents < 0:
                # Insert POSTED credit ledger entry
                credit_entry = models.LedgerEntry(
                    id=uuid.uuid4(),
                    customer_id=sub.customer_id,
                    plan_change_id=plan_change_id,
                    type="CREDIT",
                    amount_cents=abs(net_cents),
                    status="POSTED",
                    is_reconciliation=False,
                    posted_at=effective_at
                )
                db.add(credit_entry)
        else:
            # Upgrade requiring charge
            # Create PENDING payment
            payment_id = uuid.uuid4()
            payment = models.Payment(
                id=payment_id,
                plan_change_id=plan_change_id,
                merchant_reference=str(plan_change_id),
                amount_cents=net_cents,
                status="PENDING"
            )
            db.add(payment)

            # Create PENDING ledger entry
            charge_entry = models.LedgerEntry(
                id=uuid.uuid4(),
                customer_id=sub.customer_id,
                plan_change_id=plan_change_id,
                payment_id=payment_id,
                type="CHARGE",
                amount_cents=net_cents,
                status="PENDING",
                is_reconciliation=False
            )
            db.add(charge_entry)

        db.commit()
        db.refresh(new_change)
        return new_change

    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
