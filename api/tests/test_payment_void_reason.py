from pydantic import ValidationError
from app.routers.payments import VoidRequest


def test_void_reason_is_normalized():
    assert VoidRequest(reason="  Duplicate entry  ").reason == "Duplicate entry"


def test_void_reason_cannot_be_blank():
    try:
        VoidRequest(reason="   ")
    except ValidationError:
        return
    raise AssertionError("Blank reason was accepted")


def test_void_reason_cannot_exceed_database_column():
    try:
        VoidRequest(reason="a" * 256)
    except ValidationError:
        return
    raise AssertionError("Oversized reason was accepted")
