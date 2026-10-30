from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.routers import auth, schools, users, students, fees, payments, portal

Base.metadata.create_all(bind=engine)

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
