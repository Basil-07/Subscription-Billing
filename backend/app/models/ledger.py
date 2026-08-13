import uuid
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    plan_change_id = Column(UUID(as_uuid=True), ForeignKey("plan_changes.id"), nullable=False)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=True)
    type = Column(String, nullable=False) # CREDIT, CHARGE
    amount_cents = Column(BigInteger, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, POSTED, REVERSED
    is_reconciliation = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    posted_at = Column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer")
    plan_change = relationship("PlanChange")
    payment = relationship("Payment")
