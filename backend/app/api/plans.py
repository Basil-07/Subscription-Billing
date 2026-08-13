import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app import models
from app.core.database import get_db
from app.schemas.plan import PlanCreate, PlanResponse

router = APIRouter(prefix="/plans", tags=["Plans"])

@router.get("", response_model=list[PlanResponse])
def get_plans(db: Session = Depends(get_db)):
    return db.query(models.Plan).order_by(models.Plan.price_cents).all()

@router.post("", response_model=PlanResponse)
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    # Verify plan name doesn't already exist to prevent duplicate plan confusion
    exists = db.query(models.Plan).filter(models.Plan.name.ilike(payload.name)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Plan with this name already exists")
    
    new_plan = models.Plan(
        id=uuid.uuid4(),
        name=payload.name,
        price_cents=payload.price_cents
    )
    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)
    return new_plan
