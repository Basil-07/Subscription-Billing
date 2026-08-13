import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models

def test_overlapping_plan_changes(client: TestClient, db: Session):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    pro_plan_id = "a0000000-0000-4000-8000-000000000000"
    prem_plan_id = "e0000000-0000-4000-8000-000000000000"

    # Request A: Upgrade to Pro
    resp_a = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": pro_plan_id},
        headers={"Idempotency-Key": "key-concurrent-a"}
    )
    assert resp_a.status_code == 200
    pc_a_id = resp_a.json()["id"]

    # Request B: Upgrade to Premium (overlapping, before A is confirmed)
    resp_b = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": prem_plan_id},
        headers={"Idempotency-Key": "key-concurrent-b"}
    )
    assert resp_b.status_code == 200
    pc_b_id = resp_b.json()["id"]

    # Verify that plan change A has been superseded
    db.expire_all()
    pc_a = db.query(models.PlanChange).filter(models.PlanChange.id == uuid.UUID(pc_a_id)).first()
    pc_b = db.query(models.PlanChange).filter(models.PlanChange.id == uuid.UUID(pc_b_id)).first()

    assert pc_a.status == "SUPERSEDED"
    assert pc_b.status == "AWAITING_PAYMENT"

    # Verify ledger entries
    le_a = db.query(models.LedgerEntry).filter(models.LedgerEntry.plan_change_id == uuid.UUID(pc_a_id)).first()
    le_b = db.query(models.LedgerEntry).filter(models.LedgerEntry.plan_change_id == uuid.UUID(pc_b_id)).first()

    assert le_a.status == "REVERSED"
    assert le_b.status == "PENDING"
