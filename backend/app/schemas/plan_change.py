from pydantic import BaseModel, UUID4
from datetime import datetime

class PlanChangeRequest(BaseModel):
    to_plan_id: UUID4 | None # Null represents cancellation

class PlanChangeResponse(BaseModel):
    id: UUID4
    subscription_id: UUID4
    from_plan_id: UUID4 | None
    to_plan_id: UUID4 | None
    credit_cents: int
    charge_cents: int
    net_cents: int
    status: str
    requested_at: datetime
    effective_at: datetime
    idempotency_key: str
    request_hash: str

    class Config:
        from_attributes = True
