from pydantic import BaseModel, UUID4
from datetime import datetime

class PaymentResponse(BaseModel):
    id: UUID4
    plan_change_id: UUID4
    merchant_reference: str
    gateway_charge_id: str | None
    amount_cents: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
