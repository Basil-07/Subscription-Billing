import json
import hmac
import hashlib
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.core.config import settings

def sign_payload(payload_str: str, timestamp: str) -> str:
    signed = f"{timestamp}.{payload_str}"
    return hmac.new(settings.WEBHOOK_SECRET.encode(), signed.encode(), hashlib.sha256).hexdigest()

def test_late_payment_superseded_reconciliation(client: TestClient, db: Session):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    pro_plan_id = "a0000000-0000-4000-8000-000000000000"
    prem_plan_id = "e0000000-0000-4000-8000-000000000000"

    # 1. Request plan change A: Basic -> Pro (Awaiting payment)
    resp_a = client.post(
        f"/subscriptions/{sub_id}/plan-changes", 
        json={"to_plan_id": pro_plan_id}, 
        headers={"Idempotency-Key": "key-recon-a"}
    )
    assert resp_a.status_code == 200
    pc_a = resp_a.json()
    assert pc_a["status"] == "AWAITING_PAYMENT"

    # Get details of payment A
    sub_info_1 = client.get(f"/subscriptions/{sub_id}").json()
    payment_a = sub_info_1["payments"][0]
    charge_id_a = payment_a["gateway_charge_id"]

    # 2. Request plan change B: Basic -> Premium (which supersedes A)
    resp_b = client.post(
        f"/subscriptions/{sub_id}/plan-changes", 
        json={"to_plan_id": prem_plan_id}, 
        headers={"Idempotency-Key": "key-recon-b"}
    )
    assert resp_b.status_code == 200
    pc_b = resp_b.json()
    assert pc_b["status"] == "AWAITING_PAYMENT"

    # Verify that plan change A is now marked SUPERSEDED in the database
    db.expire_all()
    db_pc_a = db.query(models.PlanChange).filter(models.PlanChange.id == uuid.UUID(pc_a["id"])).first()
    assert db_pc_a.status == "SUPERSEDED"

    # Verify that the ledger entry for plan change A is marked REVERSED
    db_le_a = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.plan_change_id == uuid.UUID(pc_a["id"])
    ).first()
    assert db_le_a.status == "REVERSED"

    # 3. Simulate payment SUCCESS for A (which was superseded)
    payload_dict = {
        "gateway_event_id": "evt_recon_late_123",
        "event_type": "SUCCEEDED",
        "merchant_reference": pc_a["id"],
        "gateway_charge_id": charge_id_a,
        "amount_cents": payment_a["amount_cents"],
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload_str = json.dumps(payload_dict, separators=(',', ':'))
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig = sign_payload(payload_str, ts)

    response = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": ts, "X-Webhook-Signature": sig}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"

    # 4. Verify system state:
    # - Subscription has NOT updated to Pro (it should remain on Basic, or keep its current config)
    # - Payment is marked SUCCEEDED
    # - ReconciliationRecord is created
    # - Reconciliation LedgerEntry is created with is_reconciliation=True
    db.expire_all()
    sub = db.query(models.Subscription).filter(models.Subscription.id == uuid.UUID(sub_id)).first()
    assert str(sub.plan_id) == "b0000000-0000-4000-8000-000000000000" # remains Basic, not Pro!

    db_pay_a = db.query(models.Payment).filter(models.Payment.id == uuid.UUID(payment_a["id"])).first()
    assert db_pay_a.status == "SUCCEEDED"

    recon = db.query(models.ReconciliationRecord).filter(
        models.ReconciliationRecord.payment_id == uuid.UUID(payment_a["id"])
    ).first()
    assert recon is not None
    assert recon.status == "PENDING"
    assert recon.reason == "Late success webhook for superseded plan change"

    recon_le = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.id == recon.ledger_entry_id
    ).first()
    assert recon_le is not None
    assert recon_le.is_reconciliation is True
    assert recon_le.type == "CHARGE"
    assert recon_le.status == "PENDING"
