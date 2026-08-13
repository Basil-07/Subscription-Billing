import uuid
import hmac
import hashlib
import httpx
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy.orm import Session
from app import models
from app.core.database import get_db
from app.core.config import settings
from app.schemas.webhook import WebhookSimulateRequest
from app.services.payment import register_gateway_payment

router = APIRouter(prefix="/mock/payments", tags=["Mock Gateway"])

def generate_signature(payload_str: str, timestamp: str) -> str:
    signed_payload = f"{timestamp}.{payload_str}"
    return hmac.new(
        settings.WEBHOOK_SECRET.encode(),
        signed_payload.encode(),
        hashlib.sha256
    ).hexdigest()

async def send_webhook(webhook_url: str, event_type: str, charge_id: str, merchant_ref: str, amount: int, delay_sec: float = 0.0, duplicate_count: int = 1):
    if delay_sec > 0:
        await asyncio.sleep(delay_sec)

    # Let's generate a unique event id
    # If duplicate_count > 1, they will share the SAME event ID to test idempotency
    gateway_event_id = f"evt_{uuid.uuid4().hex[:16]}"

    for _ in range(duplicate_count):
        now_str = datetime.now(timezone.utc).isoformat()
        
        # Construct raw payload exactly as string to sign it precisely
        import json
        payload_dict = {
            "gateway_event_id": gateway_event_id,
            "event_type": event_type,
            "merchant_reference": merchant_ref,
            "gateway_charge_id": charge_id,
            "amount_cents": amount,
            "event_timestamp": now_str
        }
        
        payload_str = json.dumps(payload_dict, separators=(',', ':'))
        timestamp = str(int(datetime.now(timezone.utc).timestamp()))
        sig = generate_signature(payload_str, timestamp)

        headers = {
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": sig,
            "Content-Type": "application/json"
        }

        try:
            async with httpx.AsyncClient() as client:
                await client.post(webhook_url, content=payload_str, headers=headers, timeout=10.0)
        except Exception as e:
            print(f"Failed to deliver mock webhook: {e}")

@router.post("")
def create_payment(payload: dict, db: Session = Depends(get_db)):
    merchant_reference = payload.get("merchant_reference")
    amount_cents = payload.get("amount_cents")
    
    if not merchant_reference or not amount_cents:
        raise HTTPException(status_code=400, detail="Missing merchant_reference or amount_cents")

    gateway_charge_id = register_gateway_payment(db, merchant_reference, int(amount_cents))
    return {"gateway_charge_id": gateway_charge_id}

@router.post("/{id}/simulate")
async def simulate_event(
    id: str,
    payload: WebhookSimulateRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    charge = db.query(models.MockGatewayCharge).filter(models.MockGatewayCharge.id == id).first()
    if not charge:
        raise HTTPException(status_code=404, detail="Mock charge not found")

    webhook_url = f"{request.base_url}webhooks/payment"
    event_type = payload.event_type.upper()

    if event_type == "SUCCESS":
        charge.status = "SUCCEEDED"
        db.commit()
        background_tasks.add_task(
            send_webhook, webhook_url, "SUCCEEDED", charge.id, charge.merchant_reference, charge.amount_cents
        )
    elif event_type == "FAILURE":
        charge.status = "FAILED"
        db.commit()
        background_tasks.add_task(
            send_webhook, webhook_url, "FAILED", charge.id, charge.merchant_reference, charge.amount_cents
        )
    elif event_type == "DELAYED_SUCCESS":
        charge.status = "SUCCEEDED"
        db.commit()
        background_tasks.add_task(
            send_webhook, webhook_url, "SUCCEEDED", charge.id, charge.merchant_reference, charge.amount_cents, 5.0
        )
    elif event_type == "DUPLICATE_SUCCESS":
        charge.status = "SUCCEEDED"
        db.commit()
        background_tasks.add_task(
            send_webhook, webhook_url, "SUCCEEDED", charge.id, charge.merchant_reference, charge.amount_cents, 0.0, 3
        )
    elif event_type == "OUT_OF_ORDER":
        # Out of order: Find if there is a newer mock charge for the same subscription/customer
        # We can find all charges. Since the merchant_reference is the plan_change_id, we can find the plan change.
        pc = db.query(models.PlanChange).filter(models.PlanChange.id == charge.merchant_reference).first()
        if pc:
            # Find a newer charge for the same subscription
            newer_pc = db.query(models.PlanChange).filter(
                models.PlanChange.subscription_id == pc.subscription_id,
                models.PlanChange.created_at > pc.created_at if hasattr(models.PlanChange, 'created_at') else models.PlanChange.effective_at > pc.effective_at
            ).order_by(models.PlanChange.effective_at.desc()).first()

            if newer_pc:
                newer_charge = db.query(models.MockGatewayCharge).filter(
                    models.MockGatewayCharge.merchant_reference == str(newer_pc.id)
                ).first()
                if newer_charge:
                    # Send newer SUCCESS first, then send older FAILURE (or SUCCESS)
                    background_tasks.add_task(
                        send_webhook, webhook_url, "SUCCEEDED", newer_charge.id, newer_charge.merchant_reference, newer_charge.amount_cents
                    )
                    # We wait 1 second to ensure delivery ordering
                    await asyncio.sleep(1.0)
                    background_tasks.add_task(
                        send_webhook, webhook_url, "FAILED", charge.id, charge.merchant_reference, charge.amount_cents
                    )
                    return {"status": "Simulated B SUCCESS then A FAILURE webhooks in background"}

        # Fallback to sending success webhook for this superseded charge
        charge.status = "SUCCEEDED"
        db.commit()
        background_tasks.add_task(
            send_webhook, webhook_url, "SUCCEEDED", charge.id, charge.merchant_reference, charge.amount_cents
        )

    return {"status": f"Simulating event {event_type} in background"}

@router.post("/reset")
def reset_database(db: Session = Depends(get_db)):
    """
    Test-only endpoint to drop all tables, recreate them, and re-seed default data.
    """
    from app.core.database import Base, engine, init_db
    try:
        # Close all active connections if possible, or just drop
        Base.metadata.drop_all(bind=engine)
        init_db()
        return {"status": "success", "message": "Database reset and re-seeded successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database reset failed: {e}")

