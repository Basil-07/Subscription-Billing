import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class ReconciliationRecord(Base):
    __tablename__ = "reconciliation_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False)
    plan_change_id = Column(UUID(as_uuid=True), ForeignKey("plan_changes.id"), nullable=False)
    ledger_entry_id = Column(UUID(as_uuid=True), ForeignKey("ledger_entries.id"), nullable=False)
    reason = Column(String, nullable=False)
    status = Column(String, default="PENDING", nullable=False) # PENDING, RESOLVED
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_notes = Column(Text, nullable=True)

    payment = relationship("Payment")
    plan_change = relationship("PlanChange")
    ledger_entry = relationship("LedgerEntry")
