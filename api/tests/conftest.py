import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from app.services.auth import hash_password

TEST_DB_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_two_schools(db_session):
    from app.models.school import School
    s1 = School(code="SCH001", name="School One")
    s2 = School(code="SCH002", name="School Two")
    db_session.add_all([s1, s2])
    db_session.commit()
    db_session.refresh(s1)
    db_session.refresh(s2)

    u1 = User(email="owner1@test.com", full_name="Owner One", password_hash=hash_password("pass123"), role="owner", school_id=s1.id)
    u2 = User(email="owner2@test.com", full_name="Owner Two", password_hash=hash_password("pass123"), role="owner", school_id=s2.id)
    admin = User(email="admin@test.com", full_name="Admin", password_hash=hash_password("admin123"), role="admin", is_admin=True, school_id=None)
    db_session.add_all([u1, u2, admin])
    db_session.commit()
    return {"s1": s1, "s2": s2, "u1": u1, "u2": u2, "admin": admin}
