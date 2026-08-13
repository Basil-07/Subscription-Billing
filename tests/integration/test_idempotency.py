import pytest
from fastapi.testclient import TestClient

def test_idempotent_plan_change(client: TestClient):
    sub_id = "f0000000-0000-4000-8000-000000000000"
    target_plan_id = "a0000000-0000-4000-8000-000000000000" # Pro
    
    headers = {"Idempotency-Key": "test-key-123"}
    payload = {"to_plan_id": target_plan_id}

    # First request
    response1 = client.post(f"/subscriptions/{sub_id}/plan-changes", json=payload, headers=headers)
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["status"] == "AWAITING_PAYMENT"
    
    # Second request (same key, same payload) -> returns original result
    response2 = client.post(f"/subscriptions/{sub_id}/plan-changes", json=payload, headers=headers)
    assert response2.status_code == 200
    data2 = response2.json()
    assert data1["id"] == data2["id"]
    
    # Third request (same key, different payload) -> returns 409 Conflict
    different_payload = {"to_plan_id": "e0000000-0000-4000-8000-000000000000"} # Premium
    response3 = client.post(f"/subscriptions/{sub_id}/plan-changes", json=different_payload, headers=headers)
    assert response3.status_code == 409
    assert "Idempotency-key reuse with different request" in response3.json()["detail"]
