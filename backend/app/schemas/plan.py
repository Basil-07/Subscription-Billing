from pydantic import BaseModel, UUID4

class PlanBase(BaseModel):
    name: str
    price_cents: int

class PlanCreate(PlanBase):
    pass

class PlanResponse(PlanBase):
    id: UUID4

    class Config:
        from_attributes = True
