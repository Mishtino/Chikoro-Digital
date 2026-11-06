from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.portal import _parent_student_ids, _student_portal_student


class NoDB:
    def execute(self, *args, **kwargs):
        raise AssertionError("Unexpected database access")

    def query(self, *args, **kwargs):
        raise AssertionError("Unexpected database access")


@pytest.mark.parametrize("role,is_admin,school_id", [
    ("teacher", False, 3),
    ("parent", True, 3),
    ("parent", False, None),
])
def test_invalid_parent_identity_is_rejected(role, is_admin, school_id):
    actor = SimpleNamespace(role=role, is_admin=is_admin, school_id=school_id)
    with pytest.raises(HTTPException) as error:
        _parent_student_ids(actor, NoDB())
    assert error.value.status_code == 403


@pytest.mark.parametrize("role,is_admin,school_id", [
    ("parent", False, 3),
    ("student", True, 3),
    ("student", False, None),
])
def test_invalid_student_identity_is_rejected(role, is_admin, school_id):
    actor = SimpleNamespace(role=role, is_admin=is_admin, school_id=school_id)
    with pytest.raises(HTTPException) as error:
        _student_portal_student(actor, NoDB())
    assert error.value.status_code == 403
