from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import init_db
from app.api import plans, subscriptions, ledger, webhooks, mock_gateway, auth, customer, admin

app = FastAPI(
    title="Subscription Billing & Proration Engine",
    description="A reliable subscription billing and proration service.",
    version="0.1.0",
)

# Configure CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
        "https://subscriptionbillingengine.vercel.app",
    ] + [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_origin_regex="https://.*\\.vercel\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    if settings.AUTO_INITIALIZE_DATABASE:
        init_db()

# Register API routers
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(admin.router)
app.include_router(plans.router)
app.include_router(subscriptions.router)
app.include_router(ledger.router)
app.include_router(webhooks.router)

if settings.ENABLE_MOCK_GATEWAY:
    app.include_router(mock_gateway.router)

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "subscription-billing-engine",
    }
