import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from app import models
from app.core.database import get_db
from app.schemas.plan_change import PlanChangeRequest, PlanChangeResponse
from app.schemas.subscription import SubscriptionResponse
from app.services.plan_change import create_plan_change
from app.services.payment import register_gateway_payment, save_gateway_charge_id, mark_payment_unknown
from typing import Optional

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])

@router.get("/{id}")
def get_subscription(id: uuid.UUID, db: Session = Depends(get_db)):
    sub = db.query(models.Subscription).filter(models.Subscription.id == id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    # Get any awaiting payment plan change
    pending_pc = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == id,
        models.PlanChange.status == "AWAITING_PAYMENT"
    ).first()

    # Get all plan changes
    plan_changes = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == id
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

    # Get payments
    payments = db.query(models.Payment).join(models.PlanChange).filter(
        models.PlanChange.subscription_id == id
    ).order_by(models.Payment.created_at.desc()).all()

    # Find the customer
    customer = db.query(models.Customer).filter(models.Customer.id == sub.customer_id).first()

    return {
        "id": str(sub.id),
        "customer_id": str(sub.customer_id),
        "customer_name": customer.name if customer else "Unknown",
        "plan_id": str(sub.plan_id) if sub.plan_id else None,
        "plan_name": sub.plan.name if sub.plan else "None (Cancelled)",
        "plan_price_cents": sub.plan.price_cents if sub.plan else 0,
        "status": sub.status,
        "cycle_start": sub.cycle_start.isoformat(),
        "cycle_end": sub.cycle_end.isoformat(),
        "version": sub.version,
        "pending_plan_change": pending_pc,
        "plan_changes": plan_changes_enriched,
        "payments": payments
    }

@router.get("/{id}/proration-preview")
def preview_proration(
    id: uuid.UUID,
    to_plan_id: Optional[uuid.UUID] = None,
    effective_at_str: Optional[str] = None,
    db: Session = Depends(get_db)
):
    sub = db.query(models.Subscription).filter(models.Subscription.id == id).first()
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

    from app.services.proration import calculate_proration
    credit_cents, charge_cents, net_cents = calculate_proration(
        old_plan_price=old_price,
        new_plan_price=new_price,
        cycle_start=sub.cycle_start,
        cycle_end=sub.cycle_end,
        effective_at=effective_at
    )

    # Calculate remaining time ratio
    cycle_total = (sub.cycle_end - sub.cycle_start).total_seconds()
    # Clamp effective_at
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

@router.post("/{id}/plan-changes", response_model=PlanChangeResponse)
def change_subscription_plan(
    id: uuid.UUID,
    payload: PlanChangeRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db)
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    # 1. Create plan change record (handles idempotency, database transaction, lock)
    pc = create_plan_change(
        db=db,
        subscription_id=id,
        to_plan_id=payload.to_plan_id,
        idempotency_key=idempotency_key
    )

    # 2. If payment is required (net_cents > 0), call the mock gateway outside the transaction
    if pc.net_cents > 0 and pc.status == "AWAITING_PAYMENT":
        try:
            # Call mock gateway (invokes the service which saves to mock_gateway_charges)
            gateway_charge_id = register_gateway_payment(db, str(pc.id), pc.net_cents)
            
            # Store gateway_charge_id in a short transaction
            save_gateway_charge_id(db, pc.id, gateway_charge_id)
        except Exception as e:
            # Handle gateway timeout/failure
            mark_payment_unknown(db, pc.id)

    db.refresh(pc)
    return pc

@router.get("/{id}/plan-changes/{pcid}")
def get_plan_change(id: uuid.UUID, pcid: uuid.UUID, db: Session = Depends(get_db)):
    pc = db.query(models.PlanChange).filter(
        models.PlanChange.subscription_id == id,
        models.PlanChange.id == pcid
    ).first()
    if not pc:
        raise HTTPException(status_code=404, detail="Plan change not found")

    payment = db.query(models.Payment).filter(models.Payment.plan_change_id == pc.id).first()
    
    return {
        "plan_change": pc,
        "payment": payment
    }
