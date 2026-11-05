import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.routers import auth, schools, users, students, fees, payments, portal, paynow, results, notifications, platform_audit, platform_access, platform_staff, school_staff, school_admin, attendance

logger = logging.getLogger("chikoro.security")

# Production schema changes are applied only through reviewed migrations.
# Do not run metadata.create_all() at application startup.


# Record the effective DB role without exposing DATABASE_URL or credentials.
# This lets operators verify whether the application connection bypasses RLS.
try:
    with engine.connect() as connection:
        role = connection.execute(text("""
            select current_user,
                   coalesce((select rolsuper from pg_roles where rolname = current_user), false),
                   coalesce((select rolbypassrls from pg_roles where rolname = current_user), false)
        """)).one()
        logger.warning(
            "database_role_check user=%s superuser=%s bypass_rls=%s",
            role[0], role[1], role[2],
        )
except Exception:
    logger.exception("database_role_check_failed")


app = FastAPI(title=settings.app_name, debug=settings.debug)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name, "env": settings.env}


app.include_router(auth.router)
app.include_router(schools.router)
app.include_router(users.router)
app.include_router(students.router)
app.include_router(fees.router)
app.include_router(payments.router)
app.include_router(payments.invoices_router)
app.include_router(portal.router)
app.include_router(paynow.router)
app.include_router(results.router)
app.include_router(notifications.router)
app.include_router(platform_audit.router)
app.include_router(platform_access.router)
app.include_router(platform_staff.router)
app.include_router(school_staff.router)
app.include_router(school_admin.router)
app.include_router(attendance.router)
