from pydantic import BaseModel, UUID4
from datetime import datetime
from app.schemas.plan import PlanResponse

class SubscriptionBase(BaseModel):
    customer_id: UUID4
    plan_id: UUID4 | None
    status: str
    cycle_start: datetime
    cycle_end: datetime
    version: int

class SubscriptionResponse(SubscriptionBase):
    id: UUID4
    plan: PlanResponse | None = None

    class Config:
        from_attributes = True
