import uuid
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_change_id = Column(UUID(as_uuid=True), ForeignKey("plan_changes.id"), unique=True, nullable=False)
    merchant_reference = Column(String, unique=True, nullable=False)
    gateway_charge_id = Column(String, unique=True, nullable=True)
    amount_cents = Column(BigInteger, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, SUCCEEDED, FAILED, UNKNOWN, RECONCILIATION_REQUIRED
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(), nullable=False)

    plan_change = relationship("PlanChange")

class MockGatewayCharge(Base):
    __tablename__ = "mock_gateway_charges"

    id = Column(String, primary_key=True) # e.g. ch_...
    merchant_reference = Column(String, unique=True, nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, SUCCEEDED, FAILED
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)

