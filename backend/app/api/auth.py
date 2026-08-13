import secrets
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, status, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator

from app import models
from app.core.database import get_db
from app.services.security import hash_password, verify_password, get_current_user
from app.schemas.subscription import SubscriptionResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2)
    email: str
    password: str = Field(..., min_length=6)
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v or "." not in v or len(v) < 5:
            raise ValueError("Invalid email address format")
        return v

class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

@router.post("/register")
def register_customer(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    # Validate password confirmation
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    # Ensure email is unique
    exists = db.query(models.User).filter(models.User.email == payload.email).first()
    if exists:
        raise HTTPException(status_code=400, detail="Email is already registered")

    # Hash the password securely
    hashed = hash_password(payload.password)

    # 1. Create User
    new_user = models.User(
        id=uuid.uuid4(),
        email=payload.email,
        password_hash=hashed,
        role="CUSTOMER"
    )
    db.add(new_user)
    db.commit()

    # 2. Create Customer Profile
    new_customer = models.Customer(
        id=uuid.uuid4(),
        name=payload.name,
        user_id=new_user.id
    )
    db.add(new_customer)
    db.commit()

    # 3. Create Default Subscription (No active plan initially)
    now = datetime.now(timezone.utc)
    new_sub = models.Subscription(
        id=uuid.uuid4(),
        customer_id=new_customer.id,
        plan_id=None,
        status="CANCELLED",
        cycle_start=now,
        cycle_end=now,
        version=1
    )
    db.add(new_sub)
    db.commit()

    # 4. Generate bearer session token
    token = secrets.token_hex(32)
    session = models.UserSession(
        id=uuid.uuid4(),
        token=token,
        user_id=new_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    db.add(session)
    db.commit()

    # Log successful registration as a login event
    history = models.LoginHistory(
        id=uuid.uuid4(),
        user_id=new_user.id,
        email_attempted=payload.email,
        success=True,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        failure_reason=None
    )
    db.add(history)
    db.commit()

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": new_user.role,
        "customer_id": str(new_customer.id),
        "subscription_id": str(new_sub.id)
    }

@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")

    user = db.query(models.User).filter(models.User.email == payload.email).first()
    
    if not user:
        # Save failed attempt (no user)
        history = models.LoginHistory(
            id=uuid.uuid4(),
            user_id=None,
            email_attempted=payload.email,
            success=False,
            ip_address=ip,
            user_agent=ua,
            failure_reason="User not found"
        )
        db.add(history)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        history = models.LoginHistory(
            id=uuid.uuid4(),
            user_id=user.id,
            email_attempted=payload.email,
            success=False,
            ip_address=ip,
            user_agent=ua,
            failure_reason="Account is inactive"
        )
        db.add(history)
        db.commit()
        raise HTTPException(status_code=400, detail="Account is inactive")

    # Verify password hash
    if not verify_password(payload.password, user.password_hash):
        history = models.LoginHistory(
            id=uuid.uuid4(),
            user_id=user.id,
            email_attempted=payload.email,
            success=False,
            ip_address=ip,
            user_agent=ua,
            failure_reason="Invalid credentials"
        )
        db.add(history)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Success! Create token
    token = secrets.token_hex(32)
    session = models.UserSession(
        id=uuid.uuid4(),
        token=token,
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    db.add(session)

    # Log success audit
    user.last_login_at = datetime.now(timezone.utc)
    history = models.LoginHistory(
        id=uuid.uuid4(),
        user_id=user.id,
        email_attempted=payload.email,
        success=True,
        ip_address=ip,
        user_agent=ua,
        failure_reason=None
    )
    db.add(history)
    db.commit()

    # Find customer reference if CUSTOMER role
    customer_id = None
    subscription_id = None
    if user.role == "CUSTOMER":
        cust = db.query(models.Customer).filter(models.Customer.user_id == user.id).first()
        if cust:
            customer_id = str(cust.id)
            sub = db.query(models.Subscription).filter(models.Subscription.customer_id == cust.id).first()
            if sub:
                subscription_id = str(sub.id)

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "customer_id": customer_id,
        "subscription_id": subscription_id
    }

@router.post("/logout")
def logout(authorization: str | None = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization header")
    try:
        _, token = authorization.split(" ")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token format")
        
    db.query(models.UserSession).filter(models.UserSession.token == token).delete()
    db.commit()
    return {"detail": "Logged out successfully"}

@router.get("/me")
def get_me(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    result = {
        "id": str(current_user.id),
        "email": current_user.email,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat(),
        "last_login_at": current_user.last_login_at.isoformat() if current_user.last_login_at else None,
        "is_active": current_user.is_active
    }
    if current_user.role == "CUSTOMER":
        cust = db.query(models.Customer).filter(models.Customer.user_id == current_user.id).first()
        if cust:
            result["customer_name"] = cust.name
            result["customer_id"] = str(cust.id)
            sub = db.query(models.Subscription).filter(models.Subscription.customer_id == cust.id).first()
            if sub:
                result["subscription_id"] = str(sub.id)
    return result

@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid old password")
    
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"detail": "Password changed successfully"}
