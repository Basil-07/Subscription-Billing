import uuid
from sqlalchemy import Column, String, DateTime, func, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gateway_event_id = Column(String, unique=True, nullable=False)
    event_type = Column(String, nullable=False) # SUCCEEDED, FAILED
    merchant_reference = Column(String, nullable=False)
    gateway_charge_id = Column(String, nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=False)
    payload = Column(JSON, nullable=False)
    received_at = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    processing_status = Column(String, default="RECEIVED", nullable=False) # RECEIVED, PROCESSED, FAILED, IGNORED
    processing_result = Column(String, nullable=True)
