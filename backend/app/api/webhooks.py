import json
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.webhook import verify_webhook_signature, process_webhook_event

router = APIRouter(prefix="/webhooks/payment", tags=["Webhooks"])

@router.post("")
async def receive_payment_webhook(
    request: Request,
    x_webhook_timestamp: str = Header(..., alias="X-Webhook-Timestamp"),
    x_webhook_signature: str = Header(..., alias="X-Webhook-Signature"),
    db: Session = Depends(get_db)
):
    raw_body = await request.body()
    
    # Verify cryptographic signature and replay window
    if not verify_webhook_signature(raw_body, x_webhook_signature, x_webhook_timestamp):
        raise HTTPException(status_code=401, detail="Invalid webhook signature or expired timestamp")

    # Parse JSON payload
    try:
        payload = json.loads(raw_body.decode())
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Process webhook event in transaction
    result, code = process_webhook_event(db, payload)
    
    if code >= 400:
        raise HTTPException(status_code=code, detail=result)

    return {"status": result}
