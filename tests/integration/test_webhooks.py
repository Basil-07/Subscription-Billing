import json
import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models
from app.core.config import settings

def sign_payload(payload_str: str, timestamp: str) -> str:
    signed = f"{timestamp}.{payload_str}"
    return hmac.new(settings.WEBHOOK_SECRET.encode(), signed.encode(), hashlib.sha256).hexdigest()

def test_webhook_security_checks(client: TestClient):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000"
    
    # 1. Create a plan change requiring payment
    resp = client.post(f"/subscriptions/{sub_id}/plan-changes", json={"to_plan_id": target_plan_id}, headers={"Idempotency-Key": "key-web-1"})
    assert resp.status_code == 200
    pc_id = resp.json()["id"]

    # 2. Get payment details
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    payment = sub_info["payments"][0]
    gateway_charge_id = payment["gateway_charge_id"]

    # Prepare webhook payload
    payload_dict = {
        "gateway_event_id": "evt_test_123",
        "event_type": "SUCCEEDED",
        "merchant_reference": pc_id,
        "gateway_charge_id": gateway_charge_id,
        "amount_cents": payment["amount_cents"],
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload_str = json.dumps(payload_dict, separators=(',', ':'))

    # Invalid signature test
    response = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": str(int(datetime.now(timezone.utc).timestamp())), "X-Webhook-Signature": "bad-sig"}
    )
    assert response.status_code == 401

    # Expired timestamp test
    old_ts = str(int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()))
    sig = sign_payload(payload_str, old_ts)
    response = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": old_ts, "X-Webhook-Signature": sig}
    )
    assert response.status_code == 401

    # Valid signature test
    valid_ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig = sign_payload(payload_str, valid_ts)
    response = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": valid_ts, "X-Webhook-Signature": sig}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPLIED"

    # Duplicate delivery test (same event ID) -> returns IGNORED_DUPLICATE
    response_dup = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": valid_ts, "X-Webhook-Signature": sig}
    )
    assert response_dup.status_code == 200
    assert response_dup.json()["status"] == "IGNORED_DUPLICATE"

def test_subscription_reactivation(client: TestClient):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000" # Pro
    
    # 1. Cancel the subscription (free no-op change confirmed immediately)
    resp = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": None},
        headers={"Idempotency-Key": "reactivate-test-cancel"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "CONFIRMED"
    
    # Verify subscription is cancelled
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["status"] == "CANCELLED"
    
    # 2. Reactivate by moving to Pro plan (requiring full payment of ₹30.00 / 3000 cents)
    resp_reactivate = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": target_plan_id},
        headers={"Idempotency-Key": "reactivate-test-upgrade"}
    )
    if resp_reactivate.status_code != 200:
        print("REACTIVATE ERROR DETAIL:", resp_reactivate.json())
    assert resp_reactivate.status_code == 200
    pc = resp_reactivate.json()
    assert pc["status"] == "AWAITING_PAYMENT"
    assert pc["net_cents"] == 3000
    
    # 3. Simulate payment webhook
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    payment = sub_info["payments"][0]
    gateway_charge_id = payment["gateway_charge_id"]
    
    payload_dict = {
        "gateway_event_id": "evt_reactivate_123",
        "event_type": "SUCCEEDED",
        "merchant_reference": pc["id"],
        "gateway_charge_id": gateway_charge_id,
        "amount_cents": 3000,
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    payload_str = json.dumps(payload_dict, separators=(',', ':'))
    valid_ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig = sign_payload(payload_str, valid_ts)
    
    response = client.post(
        "/webhooks/payment",
        content=payload_str,
        headers={"X-Webhook-Timestamp": valid_ts, "X-Webhook-Signature": sig}
    )
    if response.status_code != 200:
        print("WEBHOOK ERROR DETAIL:", response.json())
    assert response.status_code == 200
    
    # Verify subscription status is ACTIVE, plan is Pro, and cycle was reset (about 30 days remaining)
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["status"] == "ACTIVE"
    assert sub_info["plan_id"] == target_plan_id
    
    cycle_start = datetime.fromisoformat(sub_info["cycle_start"])
    cycle_end = datetime.fromisoformat(sub_info["cycle_end"])
    diff = cycle_end - cycle_start
    assert 29 <= diff.days <= 31

def test_failed_change_payment_later_succeeds(client: TestClient):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000" # Pro

    # Request plan upgrade to Pro
    resp = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": target_plan_id},
        headers={"Idempotency-Key": "failed-capture-test-upgrade"}
    )
    assert resp.status_code == 200
    pc = resp.json()
    assert pc["status"] == "AWAITING_PAYMENT"

    # Get payment gateway charge reference
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    payment = sub_info["payments"][0]
    gateway_charge_id = payment["gateway_charge_id"]

    # 1. Simulate failure webhook
    fail_payload = {
        "gateway_event_id": "evt_fail_123",
        "event_type": "FAILED",
        "merchant_reference": pc["id"],
        "gateway_charge_id": gateway_charge_id,
        "amount_cents": pc["net_cents"],
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    fail_str = json.dumps(fail_payload, separators=(',', ':'))
    fail_ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig_fail = sign_payload(fail_str, fail_ts)

    res_fail = client.post(
        "/webhooks/payment",
        content=fail_str,
        headers={"X-Webhook-Timestamp": fail_ts, "X-Webhook-Signature": sig_fail}
    )
    assert res_fail.status_code == 200

    # Verify payment status is FAILED
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["status"] == "ACTIVE" # plan remains Basic
    assert sub_info["plan_name"] == "Basic"
    assert sub_info["payments"][0]["status"] == "FAILED"

    # 2. Simulate success webhook arriving later (late capture)
    success_payload = {
        "gateway_event_id": "evt_success_late_123",
        "event_type": "SUCCEEDED",
        "merchant_reference": pc["id"],
        "gateway_charge_id": gateway_charge_id,
        "amount_cents": pc["net_cents"],
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    success_str = json.dumps(success_payload, separators=(',', ':'))
    success_ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig_success = sign_payload(success_str, success_ts)

    res_success = client.post(
        "/webhooks/payment",
        content=success_str,
        headers={"X-Webhook-Timestamp": success_ts, "X-Webhook-Signature": sig_success}
    )
    assert res_success.status_code == 200

    # Verify payment status transitioned to SUCCEEDED
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["payments"][0]["status"] == "SUCCEEDED"
    
    # Plan remains Basic because the change is failed and reconciled
    assert sub_info["plan_name"] == "Basic"

    # Verify a reconciliation record exists
    recons = client.get("/reconciliations").json()
    assert len(recons) > 0
    recon_match = [r for r in recons if r["payment_id"] == payment["id"]]
    assert len(recon_match) == 1
    assert recon_match[0]["status"] == "PENDING"
    assert "failed" in recon_match[0]["reason"].lower()

def test_payment_succeeds_after_cancellation(client: TestClient):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000" # Pro

    # Request plan upgrade to Pro
    resp = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": target_plan_id},
        headers={"Idempotency-Key": "cancel-capture-test-upgrade"}
    )
    assert resp.status_code == 200
    pc = resp.json()
    assert pc["status"] == "AWAITING_PAYMENT"

    # Get payment gateway charge reference
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    payment = sub_info["payments"][0]
    gateway_charge_id = payment["gateway_charge_id"]

    # Cancel subscription immediately (should confirm immediately since cancellation has net <= 0)
    cancel_resp = client.post(
        f"/subscriptions/{sub_id}/plan-changes",
        json={"to_plan_id": None},
        headers={"Idempotency-Key": "cancel-capture-test-cancel"}
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CONFIRMED"

    # Verify subscription is CANCELLED
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["status"] == "CANCELLED"

    # Now simulate late success webhook for the Pro upgrade payment
    success_payload = {
        "gateway_event_id": "evt_success_after_cancel_123",
        "event_type": "SUCCEEDED",
        "merchant_reference": pc["id"],
        "gateway_charge_id": gateway_charge_id,
        "amount_cents": pc["net_cents"],
        "event_timestamp": datetime.now(timezone.utc).isoformat()
    }
    success_str = json.dumps(success_payload, separators=(',', ':'))
    success_ts = str(int(datetime.now(timezone.utc).timestamp()))
    sig_success = sign_payload(success_str, success_ts)

    res_success = client.post(
        "/webhooks/payment",
        content=success_str,
        headers={"X-Webhook-Timestamp": success_ts, "X-Webhook-Signature": sig_success}
    )
    assert res_success.status_code == 200

    # Verify subscription remains CANCELLED (never resurrected)
    sub_info = client.get(f"/subscriptions/{sub_id}").json()
    assert sub_info["status"] == "CANCELLED"
    assert sub_info["plan_id"] is None

    # Verify a reconciliation record was created
    recons = client.get("/reconciliations").json()
    recon_match = [r for r in recons if r["payment_id"] == payment["id"]]
    assert len(recon_match) == 1
    assert recon_match[0]["status"] == "PENDING"
    assert "cancelled" in recon_match[0]["reason"].lower() or "superseded" in recon_match[0]["reason"].lower()

