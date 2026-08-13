from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.core.database import get_db
from app.schemas.ledger import LedgerEntryResponse
from app.services.reconciliation import get_reconciliation_records, resolve_reconciliation_record
from pydantic import BaseModel

import uuid

router = APIRouter(tags=["Ledger & Reconciliation"])

class ResolutionRequest(BaseModel):
    resolution_notes: str

@router.get("/customers")
def list_customers(db: Session = Depends(get_db)):
    customers = db.query(models.Customer).all()
    results = []
    for c in customers:
        sub = db.query(models.Subscription).filter(models.Subscription.customer_id == c.id).first()
        results.append({
            "id": str(c.id),
            "name": c.name,
            "subscription_id": str(sub.id) if sub else None
        })
    return results

@router.get("/customers/{id}/ledger", response_model=list[LedgerEntryResponse])
def get_customer_ledger(id: uuid.UUID, db: Session = Depends(get_db)):
    # Check customer exists
    customer = db.query(models.Customer).filter(models.Customer.id == id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    return db.query(models.LedgerEntry).filter(
        models.LedgerEntry.customer_id == id
    ).order_by(models.LedgerEntry.created_at.desc()).all()

@router.get("/reconciliations")
def list_reconciliations(db: Session = Depends(get_db)):
    records = get_reconciliation_records(db)
    
    # Enrich with payment details
    results = []
    for r in records:
        results.append({
            "id": str(r.id),
            "payment_id": str(r.payment_id),
            "plan_change_id": str(r.plan_change_id),
            "ledger_entry_id": str(r.ledger_entry_id),
            "reason": r.reason,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            "resolution_notes": r.resolution_notes,
            "amount_cents": r.payment.amount_cents if r.payment else 0,
            "merchant_reference": r.payment.merchant_reference if r.payment else ""
        })
    return results

@router.post("/reconciliations/{id}/resolve")
def resolve_reconciliation(id: uuid.UUID, payload: ResolutionRequest, db: Session = Depends(get_db)):
    record = resolve_reconciliation_record(db, id, payload.resolution_notes)
    if not record:
        raise HTTPException(status_code=404, detail="Reconciliation record not found")
    return {"status": "resolved", "id": id}
