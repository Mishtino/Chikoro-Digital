# Chikoro Digital

SaaS school platform (staff app + student/parent portal) plus VortexTechPortal internal admin.

## Structure

- `api/` - FastAPI service
- `web/` - Next.js staff app, portal, landing
- `admin/` - Next.js VortexTechPortal
- `worker/` - background worker
- `db/` - SQL schema and migrations
- `docs/` - specs and runbooks

## Quick start (backend)

```bash
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload --port 8000
```

Run tests:

```bash
cd api
python -m pytest -q
```

## Frontend

```bash
cd web
npm install
npm run dev
```

Admin:

```bash
cd admin
npm install
npm run dev
```

## Notes

- Database defaults to SQLite for local dev. Set `DATABASE_URL` to PostgreSQL for production.
- All API queries are scoped by `school_id` taken from the JWT, never from the request body.
