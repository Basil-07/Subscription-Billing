# Subscription Billing & Proration Engine

## 1. Overview

The Subscription Billing & Proration Engine is a backend-oriented
subscription billing system designed to handle mid-cycle plan changes,
prorated billing, payment processing, asynchronous payment webhooks,
and financial ledger management.

The primary focus of the project is financial and state consistency
under unreliable external events and concurrent requests.

The system is designed to handle:

- Subscription upgrades, downgrades, and cancellations
- Mid-cycle proration
- API request idempotency
- Concurrent plan changes
- Payment state management
- Authenticated payment webhooks
- Duplicate and out-of-order webhook events
- Payment reconciliation
- Auditable financial ledger entries

A React + TypeScript frontend is included as a demonstration layer.
A deterministic mock payment gateway is used to reproduce payment
success, failure, duplicate, delayed, and out-of-order scenarios.

---

## 2. Objectives

The project is designed around the following objectives:

1. Calculate deterministic and accurate prorated charges and credits.
2. Prevent duplicate financial effects caused by API retries.
3. Safely process duplicate and out-of-order payment webhooks.
4. Serialize concurrent plan changes for the same subscription.
5. Maintain an auditable financial history.
6. Provide a clear demonstration interface for evaluating the system.

---

## 3. Proposed Architecture

The system follows a modular-monolith architecture.

```text
                    React + TypeScript
                     Demonstration UI
                            |
                       REST / JSON
                            |
                            v
                     +-------------+
                     |   FastAPI   |
                     |  API Layer  |
                     +------+------+
                            |
          +-----------------+-----------------+
          |                 |                 |
          v                 v                 v
 +----------------+ +----------------+ +----------------+
 | Plan Change    | | Payment        | | Webhook        |
 | Service        | | Service        | | Receiver       |
 |                | |                | |                |
 | Idempotency    | | Gateway        | | HMAC           |
 | State          | | Payment State  | | Event Handling |
 | Proration      | | Reconciliation | | Idempotency    |
 +-------+--------+ +-------+--------+ +-------+--------+
         |                  |                  |
         +------------------+------------------+
                            |
                            v
                    +---------------+
                    |  PostgreSQL   |
                    |               |
                    | subscriptions |
                    | plans         |
                    | plan_changes  |
                    | payments      |
                    | ledger_entries|
                    | webhook_events|
                    +-------+-------+
                            ^
                            |
                   asynchronous webhook
                            |
                   +--------+---------+
                   | Mock Payment    |
                   | Gateway         |
                   |                 |
                   | Success         |
                   | Failure         |
                   | Duplicate       |
                   | Delayed         |
                   | Out-of-order    |
                   +-----------------+

PostgreSQL acts as the authoritative source of persistent state.
Transactional updates, unique constraints, and row-level locking are
used to maintain consistency.

4. Technology Stack
Layer	Technology
Backend	Python 3.12
API Framework	FastAPI
Validation	Pydantic
ORM	SQLAlchemy
Database	PostgreSQL
Migrations	Alembic
Frontend	React + TypeScript
Frontend Build Tool	Vite
Backend Testing	Pytest
HTTP Testing	HTTPX
Linting / Formatting	Ruff
Frontend Linting	ESLint
Containerization	Docker Compose
API Documentation	OpenAPI / Swagger
5. Core Design
5.1 Proration

For a subscription change occurring during an active billing cycle,
the system calculates:

Unused value of current plan
            +
Remaining-period value of target plan
            =
Net prorated amount

The implementation uses Decimal for intermediate monetary
calculations and integer cents for persisted monetary values.

The billing-cycle end is treated as an exclusive boundary.

5.2 API Idempotency

Plan-change requests require an Idempotency-Key.

The system stores the key together with a canonical representation of
the request.

Repeated requests with the same key and identical payload return the
original operation result.

Reusing the same key with a different request is rejected.

5.3 Webhook Idempotency

Payment webhook events are identified using a unique gateway event
identifier.

Repeated delivery of the same event must not create another payment
or ledger effect.

Webhook authenticity is planned to be verified using HMAC-SHA256 and
timestamp validation.

5.4 Concurrency

Concurrent plan changes for the same subscription are serialized using
PostgreSQL row-level locking.

The subscription record acts as the serialization point, ensuring that
at most one committed pending plan-change operation exists for a
subscription.

5.5 Payment and Subscription State

Payment state is maintained independently from plan-change state.

This is required for cases where a payment succeeds after its
associated plan change has already been superseded.

The payment remains financially traceable, while the superseded
subscription transition is not reactivated.

6. In Scope

The initial implementation includes:

Subscription upgrades, downgrades, and cancellation
Mid-cycle proration
API idempotency
Concurrent plan-change handling
Mock payment processing
Authenticated and idempotent webhooks
Duplicate and out-of-order event handling
Payment reconciliation
Financial ledger
React/TypeScript demonstration frontend
Automated unit and integration tests
Docker Compose development environment
7. Out of Scope

The following are intentionally excluded:

Real Payment Provider Integration

A deterministic mock gateway is used instead so that payment success,
failure, duplication, delay, and out-of-order delivery can be
reproduced reliably during testing.

Authentication and Authorization

User authentication, authorization, OAuth, and role-based access
control are outside the billing correctness requirements of the
assessment.

Taxes, Discounts, and Multi-Currency

These are excluded to keep the pricing model focused on the core
proration and billing calculations.

Automated Dunning and Payment Retry

Automated customer collection workflows are outside the primary focus,
which is payment-state and webhook reliability.

Distributed Microservices and Kubernetes

The system uses a modular monolith because subscription, payment, and
ledger operations require strong transactional consistency. Introducing
distributed services would add unnecessary coordination complexity for
the current scope.

Production Infrastructure

High availability, autoscaling, disaster recovery, and production
observability are outside the prototype scope.

8. Project Structure
subscription-billing-engine/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   │
│   ├── alembic/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│
├── mock_gateway/
│
├── tests/
│   ├── unit/
│   └── integration/
│
├── docs/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
9. API Overview
Method	Endpoint	Purpose
GET	/plans	List available plans
GET	/subscriptions/{id}	Retrieve subscription state
POST	/subscriptions/{id}/plan-changes	Create upgrade, downgrade, or cancellation
GET	/subscriptions/{id}/plan-changes/{pcid}	Retrieve plan-change and payment state
GET	/customers/{id}/ledger	Retrieve financial history
POST	/webhooks/payment	Receive payment gateway events
POST	/mock/payments	Create a test payment
POST	/mock/payments/{id}/simulate	Simulate payment events

Full request and response contracts will be exposed through the
FastAPI-generated OpenAPI documentation.

10. Development Setup
Prerequisites

The development environment requires:

Git
Python 3.12+
Docker Desktop
Docker Compose
Node.js and npm
Start the Backend Environment
docker compose build
docker compose up -d
Run Database Migrations
docker compose exec api alembic upgrade head
Start the Frontend
cd frontend
npm install
npm run dev
Run Tests
pytest
API Documentation

Once the backend is running, FastAPI provides interactive API
documentation through its Swagger/OpenAPI interface.

11. Demonstration Scenarios

The completed implementation will demonstrate:

Scenario 1 — Upgrade
Basic → Premium
      ↓
Proration
      ↓
Payment
      ↓
Successful webhook
      ↓
Confirmed subscription
      ↓
Ledger entry
Scenario 2 — Duplicate Webhook
SUCCESS webhook
SUCCESS webhook
SUCCESS webhook

Expected result:

One financial effect
Scenario 3 — Out-of-Order Events
Newer plan change → SUCCESS
Older plan change → FAILURE

The stale event must not overwrite the newer subscription state.

Scenario 4 — Concurrent Plan Changes
Request A: Basic → Pro
Request B: Basic → Premium

Expected result:

One pending plan change
One superseded operation
Deterministic final state
Scenario 5 — Superseded Payment

A payment belonging to a superseded plan change succeeds after a
newer plan change has taken precedence.

Expected result:

Payment recorded
Old plan change remains superseded
Reconciliation required
12. Implementation Status
Completed
 Initial repository structure
 Initial architecture and design
 Scope and assumptions
 API contract
 Project documentation structure
In Development
 FastAPI backend
 PostgreSQL schema
 Proration engine
 Plan-change workflow
 API idempotency
 Mock payment gateway
 Webhook processing
 Payment reconciliation
 Financial ledger
 React frontend
 Automated tests
 Docker Compose integration
13. Design Principle

The implementation prioritizes correctness over unnecessary
complexity.

The primary correctness guarantees are:

No duplicate financial effects
No stale state resurrection
No conflicting pending plan changes
No silent loss of captured payments
Deterministic proration
Auditable financial history
14. Repository

Source code and implementation progress:

GitHub Repository:
https://github.com/ashhnaa/Subscriptionbillingengine