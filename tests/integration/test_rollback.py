import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models

def test_transaction_rollback_on_failure(client: TestClient, db: Session):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000"

    # We mock calculate_proration to raise an error, simulating a failure mid-transaction
    with patch("app.services.plan_change.calculate_proration", side_effect=RuntimeError("Simulated DB integrity failure")):
        response = client.post(
            f"/subscriptions/{sub_id}/plan-changes",
            json={"to_plan_id": target_plan_id},
            headers={"Idempotency-Key": "key-rollback-test"}
        )
        assert response.status_code == 500
        assert "Simulated DB integrity failure" in response.json()["detail"]

    # Verify that nothing was committed to the database
    db.expire_all()
    
    # 1. No plan change should exist for this idempotency key
    pc = db.query(models.PlanChange).filter(models.PlanChange.idempotency_key == "key-rollback-test").first()
    assert pc is None

    # 2. No payments should have been created
    payments = db.query(models.Payment).all()
    assert len(payments) == 0

    # 3. No ledger entries (other than the initial seeded subscription) should have been created
    ledgers = db.query(models.LedgerEntry).all()
    assert len(ledgers) == 0
