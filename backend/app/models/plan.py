import uuid
from sqlalchemy import Column, String, BigInteger
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

class Plan(Base):
    __tablename__ = "plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    price_cents = Column(BigInteger, nullable=False)
