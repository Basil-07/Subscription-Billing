import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.database import Base, get_db
from app.main import app
from app import models
from datetime import datetime, timedelta, timezone

# Use SQLite file-based DB for fast integration testing (to share connection state)
SQLALCHEMY_DATABASE_URL = "sqlite:///test.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    db_session = TestingSessionLocal()
    
    # Seed Plans
    plans = [
        models.Plan(id=uuid.UUID("b0000000-0000-4000-8000-000000000000"), name="Basic", price_cents=1000),
        models.Plan(id=uuid.UUID("a0000000-0000-4000-8000-000000000000"), name="Pro", price_cents=3000),
        models.Plan(id=uuid.UUID("e0000000-0000-4000-8000-000000000000"), name="Premium", price_cents=5000),
    ]
    db_session.add_all(plans)
    
    # Seed Customer
    customer = models.Customer(id=uuid.UUID("c0000000-0000-4000-8000-000000000000"), name="Test Customer")
    db_session.add(customer)
    db_session.commit()
    
    # Seed Subscription
    now = datetime.now(timezone.utc)
    sub = models.Subscription(
        id=uuid.UUID("f0000000-0000-4000-8000-000000000000"),
        customer_id=uuid.UUID("c0000000-0000-4000-8000-000000000000"),
        plan_id=uuid.UUID("b0000000-0000-4000-8000-000000000000"),
        status="ACTIVE",
        cycle_start=now,
        cycle_end=now + timedelta(days=30),
        version=1
    )
    db_session.add(sub)
    db_session.commit()

    try:
        yield db_session
    finally:
        db_session.close()
        Base.metadata.drop_all(bind=engine)
        import os
        if os.path.exists("test.db"):
            try:
                os.remove("test.db")
            except Exception:
                pass

@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
