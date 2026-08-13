import uuid
from sqlalchemy.orm import Session
from app import models

def register_gateway_payment(db: Session, merchant_reference: str, amount_cents: int) -> str:
    """
    Simulates registering a payment at the external mock gateway.
    Creates a MockGatewayCharge and returns a new gateway_charge_id.
    """
    gateway_charge_id = f"ch_{uuid.uuid4().hex[:16]}"
    
    # Check if a mock gateway charge already exists for this reference
    existing = db.query(models.MockGatewayCharge).filter(
        models.MockGatewayCharge.merchant_reference == merchant_reference
    ).first()
    
    if existing:
        return existing.id

    charge = models.MockGatewayCharge(
        id=gateway_charge_id,
        merchant_reference=merchant_reference,
        amount_cents=amount_cents,
        status="PENDING"
    )
    db.add(charge)
    db.commit()
    return gateway_charge_id

def save_gateway_charge_id(db: Session, plan_change_id: uuid.UUID, gateway_charge_id: str):
    """
    Updates the local Payment record with the gateway_charge_id returned by the gateway.
    """
    pc_uuid = uuid.UUID(str(plan_change_id)) if not isinstance(plan_change_id, uuid.UUID) else plan_change_id
    payment = db.query(models.Payment).filter(
        models.Payment.plan_change_id == pc_uuid
    ).first()
    if payment:
        payment.gateway_charge_id = gateway_charge_id
        db.commit()

def mark_payment_unknown(db: Session, plan_change_id: uuid.UUID):
    """
    Updates the local Payment record to UNKNOWN/RECONCILIATION_REQUIRED when the gateway call fails or times out.
    """
    pc_uuid = uuid.UUID(str(plan_change_id)) if not isinstance(plan_change_id, uuid.UUID) else plan_change_id
    payment = db.query(models.Payment).filter(
        models.Payment.plan_change_id == pc_uuid
    ).first()
    if payment:
        payment.status = "UNKNOWN"
        db.commit()
