# Vercel + Aiven deployment

Deploy this repository as **two Vercel projects**. This keeps the Vite static
site and the FastAPI serverless application independent while sharing the same
repository.

## 1. Create Aiven PostgreSQL

Create an Aiven PostgreSQL service with public internet access. Copy its
service URI and set the database environment variable using the SQLAlchemy
Psycopg 3 scheme:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require
```

Use the exact Aiven host, port, user, password, and database name. If your
Aiven service requires certificate verification, add its CA certificate to the
deployment and use `sslrootcert` in the URI; `sslmode=require` encrypts the
connection but does not verify the server certificate.

Initialize a brand-new database once, from a trusted machine (not in a Vercel
function):

```powershell
cd backend
$env:DATABASE_URL='postgresql+psycopg://...?...'
python scripts/initialize_database.py
```

This currently creates the schema and demo users, including the documented
demo credentials. Do not run it against a database that should not contain
demo data.

## 2. Deploy the backend

Import the Git repository into Vercel and create a project whose **Root
Directory** is `backend`. Vercel discovers `app/app.py` as the FastAPI entry
point. Set these production environment variables:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME?sslmode=require
WEBHOOK_SECRET=<a-long-random-secret>
APP_ENV=production
ENABLE_MOCK_GATEWAY=false
AUTO_INITIALIZE_DATABASE=false
CORS_ORIGINS=https://YOUR-FRONTEND.vercel.app
```

Deploy and verify `https://YOUR-BACKEND.vercel.app/health` returns an `ok`
response.

## 3. Deploy the frontend

Create another Vercel project from the same repository with **Root Directory**
set to `frontend`. The included `vercel.json` builds the Vite application and
serves its SPA routes. Set:

```text
VITE_API_URL=https://YOUR-BACKEND.vercel.app
```

Redeploy the frontend after setting the variable, then add its final Vercel URL
to the backend `CORS_ORIGINS` and redeploy the backend.

## Operational notes

- Vercel Functions can restart or scale at any time; they deliberately do not
  create tables or seed data at startup.
- Keep Aiven in a region near your selected Vercel function region to minimise
  database latency.
- The bundled mock gateway is disabled for production. Its delayed background
  webhook simulations are not suitable for serverless production use.
