import hashlib
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from fastapi import Header, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app import models
from app.core.config import settings

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    # 100,000 iterations PBKDF2 HMAC-SHA256
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return f"pbkdf2_sha256$100000${salt}${key.hex()}"

def verify_password(password: str, hashed: str) -> bool:
    try:
        parts = hashed.split('$')
        if len(parts) != 4:
            return False
        algo, iterations, salt, key_hex = parts
        if algo != "pbkdf2_sha256":
            return False
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), int(iterations))
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def get_current_user(authorization: str | None = Header(None), db: Session = Depends(get_db)) -> models.User:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header"
        )
    try:
        token_type, token = authorization.split(" ")
        if token_type.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format"
        )
        
    session = db.query(models.UserSession).filter(
        models.UserSession.token == token,
        models.UserSession.expires_at > datetime.now(timezone.utc)
    ).first()
    
    if not session or not session.user or not session.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session token"
        )
        
    return session.user

def get_current_customer(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)) -> models.Customer:
    if current_user.role != "CUSTOMER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires customer role"
        )
    customer = db.query(models.Customer).filter(models.Customer.user_id == current_user.id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer profile not found"
        )
    return customer

def require_admin(current_user: models.User = Depends(get_current_user)) -> models.User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires administrator privileges"
        )
    return current_user
