from pydantic import BaseModel
from datetime import datetime

class WebhookSimulateRequest(BaseModel):
    event_type: str # SUCCESS, FAILURE, DELAYED_SUCCESS, DUPLICATE_SUCCESS, OUT_OF_ORDER

class WebhookPayload(BaseModel):
    gateway_event_id: str
    event_type: str # SUCCEEDED, FAILED
    merchant_reference: str
    gateway_charge_id: str
    amount_cents: int
    event_timestamp: datetime
