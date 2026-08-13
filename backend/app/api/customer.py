import uuid
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional

from app import models
from app.core.database import get_db
from app.services.security import get_current_customer
from app.schemas.plan_change import PlanChangeRequest, PlanChangeResponse
from app.services.plan_change import create_plan_change
from app.services.payment import register_gateway_payment, save_gateway_charge_id, mark_payment_unknown
from app.services.proration import calculate_proration

router = APIRouter(prefix="/customer", tags=["Customer Portal"])

@router.get("/subscription")
def get_customer_subscription(customer: models.Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    sub = db.query(models.Subscription).filter(models.Subscription.customer_id == customer.id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    # Get any awaiting payment plan change
    pending_pc = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == sub.id,
        models.PlanChange.status == "AWAITING_PAYMENT"
    ).first()

    # Get all plan changes
    plan_changes = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == sub.id
    ).order_by(models.PlanChange.effective_at.desc()).all()

    plan_changes_enriched = []
    for pc in plan_changes:
        from_plan = db.query(models.Plan).filter(models.Plan.id == pc.from_plan_id).first() if pc.from_plan_id else None
        to_plan = db.query(models.Plan).filter(models.Plan.id == pc.to_plan_id).first() if pc.to_plan_id else None
        plan_changes_enriched.append({
            "id": str(pc.id),
            "subscription_id": str(pc.subscription_id),
            "from_plan_id": str(pc.from_plan_id) if pc.from_plan_id else None,
            "from_plan_name": from_plan.name if from_plan else "None (Cancelled)",
            "to_plan_id": str(pc.to_plan_id) if pc.to_plan_id else None,
            "to_plan_name": to_plan.name if to_plan else "None (Cancelled)",
            "credit_cents": pc.credit_cents,
            "charge_cents": pc.charge_cents,
            "net_cents": pc.net_cents,
            "status": pc.status,
            "requested_at": pc.requested_at.isoformat(),
            "effective_at": pc.effective_at.isoformat()
        })

    # Get payments (do not expose gateway charge IDs to customers as per instructions)
    payments = db.query(models.Payment).join(models.PlanChange).filter(
        models.PlanChange.subscription_id == sub.id
    ).order_by(models.Payment.created_at.desc()).all()
    
    payments_safe = [{
        "id": str(p.id),
        "plan_change_id": str(p.plan_change_id),
        "merchant_reference": p.merchant_reference,
        "amount_cents": p.amount_cents,
        "status": p.status,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat()
    } for p in payments]

    return {
        "id": str(sub.id),
        "customer_id": str(sub.customer_id),
        "customer_name": customer.name,
        "plan_id": str(sub.plan_id) if sub.plan_id else None,
        "plan_name": sub.plan.name if sub.plan else "None (Cancelled)",
        "plan_price_cents": sub.plan.price_cents if sub.plan else 0,
        "status": sub.status,
        "cycle_start": sub.cycle_start.isoformat(),
        "cycle_end": sub.cycle_end.isoformat(),
        "version": sub.version,
        "pending_plan_change": pending_pc,
        "plan_changes": plan_changes_enriched,
        "payments": payments_safe
    }

@router.get("/ledger")
def get_customer_ledger(customer: models.Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    entries = db.query(models.LedgerEntry).filter(
        models.LedgerEntry.customer_id == customer.id
    ).order_by(models.LedgerEntry.created_at.desc()).all()
    
    # Return safe ledger entries (without exposing database internal fields except types and status)
    return [{
        "id": str(e.id),
        "customer_id": str(e.customer_id),
        "plan_change_id": str(e.plan_change_id),
        "payment_id": str(e.payment_id) if e.payment_id else None,
        "type": e.type,
        "amount_cents": e.amount_cents,
        "status": e.status,
        "is_reconciliation": e.is_reconciliation,
        "created_at": e.created_at.isoformat(),
        "posted_at": e.posted_at.isoformat() if e.posted_at else None
    } for e in entries]

@router.get("/plan-changes")
def get_customer_plan_changes(customer: models.Customer = Depends(get_current_customer), db: Session = Depends(get_db)):
    sub = db.query(models.Subscription).filter(models.Subscription.customer_id == customer.id).first()
    if not sub:
        return []
    
    plan_changes = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == sub.id
    ).order_by(models.PlanChange.effective_at.desc()).all()

    result = []
    for pc in plan_changes:
        from_plan = db.query(models.Plan).filter(models.Plan.id == pc.from_plan_id).first() if pc.from_plan_id else None
        to_plan = db.query(models.Plan).filter(models.Plan.id == pc.to_plan_id).first() if pc.to_plan_id else None
        result.append({
            "id": str(pc.id),
            "subscription_id": str(pc.subscription_id),
            "from_plan_id": str(pc.from_plan_id) if pc.from_plan_id else None,
            "from_plan_name": from_plan.name if from_plan else "None (Cancelled)",
            "to_plan_id": str(pc.to_plan_id) if pc.to_plan_id else None,
            "to_plan_name": to_plan.name if to_plan else "None (Cancelled)",
            "credit_cents": pc.credit_cents,
            "charge_cents": pc.charge_cents,
            "net_cents": pc.net_cents,
            "status": pc.status,
            "requested_at": pc.requested_at.isoformat(),
            "effective_at": pc.effective_at.isoformat()
        })
    return result

@router.get("/proration-preview")
def get_customer_proration_preview(
    to_plan_id: Optional[uuid.UUID] = None,
    effective_at_str: Optional[str] = None,
    customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    sub = db.query(models.Subscription).filter(models.Subscription.customer_id == customer.id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    old_plan = db.query(models.Plan).filter(models.Plan.id == sub.plan_id).first()
    old_price = old_plan.price_cents if old_plan else 0

    if to_plan_id:
        target_plan = db.query(models.Plan).filter(models.Plan.id == to_plan_id).first()
        if not target_plan:
            raise HTTPException(status_code=400, detail="Target plan not found")
        new_price = target_plan.price_cents
    else:
        new_price = 0

    if effective_at_str:
        try:
            effective_at = datetime.fromisoformat(effective_at_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid effective_at timestamp format")
    else:
        effective_at = datetime.now(timezone.utc)

    if sub.plan_id is None:
        credit_cents = 0
        charge_cents = new_price
        net_cents = new_price
        ratio = 1.0
        clamped_effective = effective_at
    else:
        credit_cents, charge_cents, net_cents = calculate_proration(
            old_plan_price=old_price,
            new_plan_price=new_price,
            cycle_start=sub.cycle_start,
            cycle_end=sub.cycle_end,
            effective_at=effective_at
        )

        cycle_total = (sub.cycle_end - sub.cycle_start).total_seconds()
        clamped_effective = effective_at
        if clamped_effective < sub.cycle_start:
            clamped_effective = sub.cycle_start
        if clamped_effective > sub.cycle_end:
            clamped_effective = sub.cycle_end
        cycle_rem = (sub.cycle_end - clamped_effective).total_seconds()
        ratio = float(cycle_rem / cycle_total) if cycle_total > 0 else 0.0

    return {
        "from_plan_id": str(sub.plan_id) if sub.plan_id else None,
        "from_plan_name": old_plan.name if old_plan else "None",
        "to_plan_id": str(to_plan_id) if to_plan_id else None,
        "to_plan_name": target_plan.name if to_plan_id and target_plan else "None (Cancel)",
        "credit_cents": credit_cents,
        "charge_cents": charge_cents,
        "net_cents": net_cents,
        "remaining_ratio": ratio,
        "effective_at": clamped_effective.isoformat()
    }

@router.post("/plan-changes", response_model=PlanChangeResponse)
def apply_customer_plan_change(
    payload: PlanChangeRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    customer: models.Customer = Depends(get_current_customer),
    db: Session = Depends(get_db)
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    sub = db.query(models.Subscription).filter(models.Subscription.customer_id == customer.id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")

    pc = create_plan_change(
        db=db,
        subscription_id=sub.id,
        to_plan_id=payload.to_plan_id,
        idempotency_key=idempotency_key
    )

    if pc.net_cents > 0 and pc.status == "AWAITING_PAYMENT":
        try:
            gateway_charge_id = register_gateway_payment(db, str(pc.id), pc.net_cents)
            save_gateway_charge_id(db, pc.id, gateway_charge_id)
        except Exception:
            mark_payment_unknown(db, pc.id)

    db.refresh(pc)
    return pc
