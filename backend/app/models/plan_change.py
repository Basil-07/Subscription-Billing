import uuid
from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

class PlanChange(Base):
    __tablename__ = "plan_changes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id"), nullable=False)
    from_plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True)
    to_plan_id = Column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=True) # Null means cancellation
    credit_cents = Column(BigInteger, default=0, nullable=False)
    charge_cents = Column(BigInteger, default=0, nullable=False)
    net_cents = Column(BigInteger, default=0, nullable=False)
    status = Column(String, default="AWAITING_PAYMENT", nullable=False) # AWAITING_PAYMENT, CONFIRMED, FAILED, SUPERSEDED
    requested_at = Column(DateTime(timezone=True), nullable=False)
    effective_at = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String, nullable=False)
    request_hash = Column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("subscription_id", "idempotency_key", name="uq_plan_change_sub_idem"),
    )

    subscription = relationship("Subscription")
    from_plan = relationship("Plan", foreign_keys=[from_plan_id])
    to_plan = relationship("Plan", foreign_keys=[to_plan_id])
