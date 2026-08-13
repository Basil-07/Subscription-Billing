import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, desc, asc
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app import models
from app.core.database import get_db, Base, engine, init_db
from app.core.config import settings
from app.services.security import require_admin
from app.services.reconciliation import resolve_reconciliation_record

router = APIRouter(prefix="/admin", tags=["Admin Portal"], dependencies=[Depends(require_admin)])

class ReconciliationResolveRequest(BaseModel):
    resolution_notes: str

@router.get("/customers")
def get_customers(
    name: Optional[str] = None,
    email: Optional[str] = None,
    status: Optional[str] = None,
    plan_id: Optional[uuid.UUID] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Customer).join(models.User, models.Customer.user_id == models.User.id)
    
    if name:
        query = query.filter(models.Customer.name.ilike(f"%{name}%"))
    if email:
        query = query.filter(models.User.email.ilike(f"%{email}%"))
        
    customers = query.all()
    
    results = []
    for c in customers:
        sub = db.query(models.Subscription).filter(models.Subscription.customer_id == c.id).first()
        
        # Apply filters at database/logical level
        if status and (not sub or sub.status != status):
            continue
        if plan_id and (not sub or sub.plan_id != plan_id):
            continue
            
        results.append({
            "id": str(c.id),
            "name": c.name,
            "email": c.user.email,
            "is_active": c.user.is_active,
            "created_at": c.user.created_at.isoformat(),
            "last_login_at": c.user.last_login_at.isoformat() if c.user.last_login_at else None,
            "subscription_id": str(sub.id) if sub else None,
            "plan_name": sub.plan.name if sub and sub.plan else "None (Cancelled)",
            "status": sub.status if sub else "INACTIVE"
        })
    return results

@router.get("/customers/{id}")
def get_customer_profile(id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(models.Customer).filter(models.Customer.id == id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    sub = db.query(models.Subscription).filter(models.Subscription.customer_id == c.id).first()
    
    # Login History
    logins = db.query(models.LoginHistory).filter(models.LoginHistory.user_id == c.user_id).order_by(models.LoginHistory.login_at.desc()).all()
    
    # Plan Changes
    plan_changes = []
    payments = []
    ledger = []
    reconciliations = []
    
    if sub:
        pcs = db.query(models.PlanChange).filter(
            models.PlanChange.subscription_id == sub.id
        ).order_by(models.PlanChange.effective_at.desc()).all()
        
        for pc in pcs:
            from_plan = db.query(models.Plan).filter(models.Plan.id == pc.from_plan_id).first() if pc.from_plan_id else None
            to_plan = db.query(models.Plan).filter(models.Plan.id == pc.to_plan_id).first() if pc.to_plan_id else None
            plan_changes.append({
                "id": str(pc.id),
                "from_plan_name": from_plan.name if from_plan else "None (Cancelled)",
                "to_plan_name": to_plan.name if to_plan else "None (Cancelled)",
                "credit_cents": pc.credit_cents,
                "charge_cents": pc.charge_cents,
                "net_cents": pc.net_cents,
                "status": pc.status,
                "requested_at": pc.requested_at.isoformat(),
                "effective_at": pc.effective_at.isoformat(),
                "idempotency_key": pc.idempotency_key
            })
            
        pays = db.query(models.Payment).join(models.PlanChange).filter(
            models.PlanChange.subscription_id == sub.id
        ).order_by(models.Payment.created_at.desc()).all()
        payments = [{
            "id": str(p.id),
            "plan_change_id": str(p.plan_change_id),
            "merchant_reference": p.merchant_reference,
            "gateway_charge_id": p.gateway_charge_id,
            "amount_cents": p.amount_cents,
            "status": p.status,
            "created_at": p.created_at.isoformat()
        } for p in pays]

    ledgers = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.customer_id == c.id
    ).order_by(models.LedgerEntry.created_at.desc()).all()
    ledger = [{
        "id": str(e.id),
        "type": e.type,
        "amount_cents": e.amount_cents,
        "status": e.status,
        "is_reconciliation": e.is_reconciliation,
        "created_at": e.created_at.isoformat(),
        "posted_at": e.posted_at.isoformat() if e.posted_at else None
    } for e in ledgers]

    recons = db.query(models.ReconciliationRecord).join(models.PlanChange).filter(
        models.PlanChange.subscription_id == (sub.id if sub else None)
    ).order_by(models.ReconciliationRecord.created_at.desc()).all()
    reconciliations = [{
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
        "merchant_reference": r.payment.merchant_reference if r.payment else "Unknown"
    } for r in recons]

    # Webhook Events
    webhooks = db.query(models.WebhookEvent).order_by(models.WebhookEvent.received_at.desc()).all()
    webhook_list = [{
        "id": str(w.id),
        "gateway_event_id": w.gateway_event_id,
        "event_type": w.event_type,
        "merchant_reference": w.merchant_reference,
        "processing_status": w.processing_status,
        "processing_result": w.processing_result,
        "received_at": w.received_at.isoformat(),
        "processed_at": w.processed_at.isoformat() if w.processed_at else None
    } for w in webhooks if w.merchant_reference in [p["merchant_reference"] for p in payments] or w.merchant_reference in [pc["id"] for pc in plan_changes]]

    return {
        "id": str(c.id),
        "name": c.name,
        "email": c.user.email,
        "created_at": c.user.created_at.isoformat(),
        "last_login_at": c.user.last_login_at.isoformat() if c.user.last_login_at else None,
        "logins": [{
            "login_at": l.login_at.isoformat(),
            "success": l.success,
            "ip_address": l.ip_address,
            "user_agent": l.user_agent,
            "failure_reason": l.failure_reason
        } for l in logins],
        "subscription": {
            "id": str(sub.id) if sub else None,
            "plan_name": sub.plan.name if sub and sub.plan else "None (Cancelled)",
            "plan_price_cents": sub.plan.price_cents if sub and sub.plan else 0,
            "status": sub.status if sub else "INACTIVE",
            "cycle_start": sub.cycle_start.isoformat() if sub else None,
            "cycle_end": sub.cycle_end.isoformat() if sub else None
        } if sub else None,
        "plan_changes": plan_changes,
        "payments": payments,
        "ledger": ledger,
        "reconciliations": reconciliations,
        "webhooks": webhook_list
    }

@router.get("/customers/{id}/login-history")
def get_customer_login_history(id: uuid.UUID, db: Session = Depends(get_db)):
    c = db.query(models.Customer).filter(models.Customer.id == id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Customer not found")
    logins = db.query(models.LoginHistory).filter(models.LoginHistory.user_id == c.user_id).order_by(models.LoginHistory.login_at.desc()).all()
    return [{
        "login_at": l.login_at.isoformat(),
        "success": l.success,
        "ip_address": l.ip_address,
        "user_agent": l.user_agent,
        "failure_reason": l.failure_reason
    } for l in logins]

@router.get("/reconciliations")
def get_admin_reconciliations(db: Session = Depends(get_db)):
    recons = db.query(models.ReconciliationRecord).order_by(models.ReconciliationRecord.created_at.desc()).all()
    return [{
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
        "merchant_reference": r.payment.merchant_reference if r.payment else "Unknown"
    } for r in recons]

@router.post("/reconciliations/{id}/resolve")
def resolve_admin_reconciliation(id: uuid.UUID, payload: ReconciliationResolveRequest, db: Session = Depends(get_db)):
    try:
        resolve_reconciliation_record(db, id, payload.resolution_notes)
        return {"detail": "Reconciliation record resolved successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/login-history")
def get_global_login_history(db: Session = Depends(get_db)):
    logins = db.query(models.LoginHistory).order_by(models.LoginHistory.login_at.desc()).all()
    return [{
        "id": str(l.id),
        "email_attempted": l.email_attempted,
        "login_at": l.login_at.isoformat(),
        "success": l.success,
        "ip_address": l.ip_address,
        "user_agent": l.user_agent,
        "failure_reason": l.failure_reason
    } for l in logins]

@router.get("/ledger")
def get_global_ledger(
    customer_id: Optional[uuid.UUID] = None,
    type: Optional[str] = None,
    status: Optional[str] = None,
    sort: Optional[str] = "desc",
    db: Session = Depends(get_db)
):
    query = db.query(models.LedgerEntry)
    
    if customer_id:
        query = query.filter(models.LedgerEntry.customer_id == customer_id)
    if type:
        query = query.filter(models.LedgerEntry.type == type)
    if status:
        query = query.filter(models.LedgerEntry.status == status)
        
    if sort == "asc":
        query = query.order_by(asc(models.LedgerEntry.created_at))
    else:
        query = query.order_by(desc(models.LedgerEntry.created_at))
        
    entries = query.all()
    
    results = []
    for e in entries:
        cust = db.query(models.Customer).filter(models.Customer.id == e.customer_id).first()
        results.append({
            "id": str(e.id),
            "customer_name": cust.name if cust else "Unknown",
            "type": e.type,
            "amount_cents": e.amount_cents,
            "status": e.status,
            "is_reconciliation": e.is_reconciliation,
            "created_at": e.created_at.isoformat(),
            "posted_at": e.posted_at.isoformat() if e.posted_at else None
        })
    return results

@router.post("/system/reset")
def reset_db_endpoint(db: Session = Depends(get_db)):
    if not settings.ENABLE_MOCK_GATEWAY:
        raise HTTPException(status_code=403, detail="Reset is disabled in production")
        
    # Drop and recreate all tables
    Base.metadata.drop_all(bind=engine)
    init_db()
    return {"detail": "Database reset and seeded successfully"}
