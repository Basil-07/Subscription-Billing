from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
from datetime import datetime, timedelta, timezone
import uuid

import sys

db_url = settings.DATABASE_URL
if "pytest" in sys.modules:
    db_url = "sqlite:///test.db"
elif db_url and db_url.startswith("postgres://"):
    # Aiven commonly supplies postgres:// URLs.  This project uses psycopg 3,
    # so make the SQLAlchemy driver explicit rather than falling back to the
    # unavailable psycopg2 dialect.
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # Import models inside to avoid circular dependencies
    from app import models
    from sqlalchemy import text
    Base.metadata.create_all(bind=engine)

    # If running with Postgres, alter schema dynamically
    try:
        with engine.begin() as conn:
            if "postgresql" in engine.url.drivername:
                conn.execute(text("ALTER TABLE plan_changes ALTER COLUMN from_plan_id DROP NOT NULL"))
                conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) UNIQUE"))
    except Exception as err:
        print(f"Altering table schema failed: {err}")

    db = SessionLocal()
    try:
        # Seed Plans
        plans_data = [
            {"id": uuid.UUID("b0000000-0000-4000-8000-000000000000"), "name": "Basic", "price_cents": 1000},
            {"id": uuid.UUID("a0000000-0000-4000-8000-000000000000"), "name": "Pro", "price_cents": 3000},
            {"id": uuid.UUID("e0000000-0000-4000-8000-000000000000"), "name": "Premium", "price_cents": 5000},
        ]
        
        for plan_info in plans_data:
            exists = db.query(models.Plan).filter(models.Plan.id == plan_info["id"]).first()
            if not exists:
                plan = models.Plan(
                    id=plan_info["id"],
                    name=plan_info["name"],
                    price_cents=plan_info["price_cents"]
                )
                db.add(plan)
        db.commit()

        # Import password hasher
        from app.services.security import hash_password

        # Seed Admin User
        admin_id = uuid.UUID("d0000000-0000-4000-8000-000000000000")
        exists_admin = db.query(models.User).filter(models.User.id == admin_id).first()
        if not exists_admin:
            admin_user = models.User(
                id=admin_id,
                email="admin@prora.com",
                password_hash=hash_password("adminpassword123"),
                role="ADMIN"
            )
            db.add(admin_user)
            db.commit()

        # Seed Multiple Customers & Subscriptions
        customers_to_seed = [
            {
                "user_id": uuid.UUID("d0000000-0000-4000-8000-000000000001"),
                "email": "customer_a@prora.com",
                "cust_id": uuid.UUID("c0000000-0000-4000-8000-000000000000"),
                "name": "Demo Customer A (Startup Corp)",
                "sub_id": uuid.UUID("f0000000-0000-4000-8000-000000000000"),
                "plan_id": uuid.UUID("b0000000-0000-4000-8000-000000000000") # Basic Plan
            },
            {
                "user_id": uuid.UUID("d0000000-0000-4000-8000-000000000002"),
                "email": "customer_b@prora.com",
                "cust_id": uuid.UUID("c0000000-0000-4000-8000-000000000001"),
                "name": "Demo Customer B (SaaS Enterprises)",
                "sub_id": uuid.UUID("f0000000-0000-4000-8000-000000000001"),
                "plan_id": uuid.UUID("a0000000-0000-4000-8000-000000000000") # Pro Plan
            },
            {
                "user_id": uuid.UUID("d0000000-0000-4000-8000-000000000003"),
                "email": "customer_c@prora.com",
                "cust_id": uuid.UUID("c0000000-0000-4000-8000-000000000002"),
                "name": "Demo Customer C (Global Logistics)",
                "sub_id": uuid.UUID("f0000000-0000-4000-8000-000000000002"),
                "plan_id": uuid.UUID("e0000000-0000-4000-8000-000000000000") # Premium Plan
            }
        ]

        now = datetime.now(timezone.utc)
        for seed in customers_to_seed:
            # Seed Customer User
            exists_user = db.query(models.User).filter(models.User.id == seed["user_id"]).first()
            if not exists_user:
                user = models.User(
                    id=seed["user_id"],
                    email=seed["email"],
                    password_hash=hash_password("password123"),
                    role="CUSTOMER"
                )
                db.add(user)
                db.commit()

            # Seed Customer
            exists_cust = db.query(models.Customer).filter(models.Customer.id == seed["cust_id"]).first()
            if not exists_cust:
                customer = models.Customer(
                    id=seed["cust_id"],
                    name=seed["name"],
                    user_id=seed["user_id"]
                )
                db.add(customer)
                db.commit()
            else:
                # Update user_id reference if missing
                if not exists_cust.user_id:
                    exists_cust.user_id = seed["user_id"]
                    db.commit()

            # Seed Subscription
            exists_sub = db.query(models.Subscription).filter(models.Subscription.id == seed["sub_id"]).first()
            if not exists_sub:
                subscription = models.Subscription(
                    id=seed["sub_id"],
                    customer_id=seed["cust_id"],
                    plan_id=seed["plan_id"],
                    status="ACTIVE",
                    cycle_start=now,
                    cycle_end=now + timedelta(days=30),
                    version=1
                )
                db.add(subscription)
                db.commit()

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()
