import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app import models

def test_auth_registration_and_login_flow(client: TestClient):
    # 1. Register a new customer
    payload = {
        "name": "Acme Corp",
        "email": "acme@example.com",
        "password": "securepassword123",
        "confirm_password": "securepassword123"
    }
    
    resp_reg = client.post("/auth/register", json=payload)
    assert resp_reg.status_code == 200
    reg_data = resp_reg.json()
    assert "access_token" in reg_data
    assert reg_data["role"] == "CUSTOMER"
    
    token = reg_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify registration seeded a customer and initial subscription
    resp_me = client.get("/auth/me", headers=headers)
    assert resp_me.status_code == 200
    me_data = resp_me.json()
    assert me_data["email"] == "acme@example.com"
    assert me_data["customer_name"] == "Acme Corp"
    assert "customer_id" in me_data
    assert "subscription_id" in me_data

    # Check login history (success for registration)
    resp_history = client.get(f"/admin/customers/{me_data['customer_id']}/login-history", headers=headers)
    assert resp_history.status_code == 403 # blocked for CUSTOMER role!

    # 2. Try duplicate registration
    resp_dup = client.post("/auth/register", json=payload)
    assert resp_dup.status_code == 400
    assert "already registered" in resp_dup.json()["detail"]

    # 3. Successful login
    login_payload = {
        "email": "acme@example.com",
        "password": "securepassword123"
    }
    resp_login = client.post("/auth/login", json=login_payload)
    assert resp_login.status_code == 200
    login_data = resp_login.json()
    assert "access_token" in login_data

    # 4. Failed login (bad password)
    bad_login_payload = {
        "email": "acme@example.com",
        "password": "wrongpassword"
    }
    resp_bad = client.post("/auth/login", json=bad_login_payload)
    assert resp_bad.status_code == 401
    assert "Invalid email or password" in resp_bad.json()["detail"]

def test_auth_authorization_limits(client: TestClient):
    # Register customer
    cust_payload = {
        "name": "Customer User",
        "email": "customer@example.com",
        "password": "password123",
        "confirm_password": "password123"
    }
    cust_resp = client.post("/auth/register", json=cust_payload).json()
    cust_token = cust_resp["access_token"]
    cust_headers = {"Authorization": f"Bearer {cust_token}"}

    # 1. Customer attempts to fetch admin API
    resp_admin_list = client.get("/admin/customers", headers=cust_headers)
    assert resp_admin_list.status_code == 403
    assert "privileges" in resp_admin_list.json()["detail"] or "role" in resp_admin_list.json()["detail"]

    # 2. Log in as Seeded Admin
    admin_payload = {
        "email": "admin@prora.com",
        "password": "adminpassword123"
    }
    admin_resp = client.post("/auth/login", json=admin_payload).json()
    admin_token = admin_resp["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin requests admin API (allowed)
    resp_admin_success = client.get("/admin/customers", headers=admin_headers)
    assert resp_admin_success.status_code == 200

    # 3. Admin attempts to call customer portal endpoint (blocked since admin is not a customer!)
    resp_cust_portal = client.get("/customer/subscription", headers=admin_headers)
    assert resp_cust_portal.status_code == 403
    assert "customer role" in resp_cust_portal.json()["detail"].lower()
