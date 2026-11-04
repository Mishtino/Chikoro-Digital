from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine, SessionLocal
from app.routers import auth, schools, users, students, fees, payments, portal, paynow, results, notifications
from app.models.user import User
from app.services.auth import hash_password


Base.metadata.create_all(bind=engine)

# Optional first-install bootstrap. Credentials must be provided through the
# deployment's secret environment variables; no usable default account exists.
if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
    _db = SessionLocal()
    try:
        if not _db.query(User).filter(User.email == settings.bootstrap_admin_email).first():
            _db.add(User(
                email=settings.bootstrap_admin_email,
                full_name="Vortex Technologies",
                password_hash=hash_password(settings.bootstrap_admin_password),
                role="admin",
                is_admin=True,
                school_id=None,
            ))
            _db.commit()
    finally:
        _db.close()


app = FastAPI(title=settings.app_name, debug=settings.debug)

origins = [o.strip().rstrip("/") for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    # Render's default health probe checks / unless a custom health path is set.
    return {"status": "ok", "app": settings.app_name}


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
