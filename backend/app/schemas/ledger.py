from pydantic import BaseModel, UUID4
from datetime import datetime

class LedgerEntryResponse(BaseModel):
    id: UUID4
    customer_id: UUID4
    plan_change_id: UUID4
    payment_id: UUID4 | None
    type: str # CREDIT, CHARGE
    amount_cents: int
    status: str # PENDING, POSTED, REVERSED
    is_reconciliation: bool
    created_at: datetime
    posted_at: datetime | None

    class Config:
        from_attributes = True
