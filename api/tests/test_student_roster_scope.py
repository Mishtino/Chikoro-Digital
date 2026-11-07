"""Regression coverage for student roster tenant boundaries."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.students import get_student, list_students


class NoDatabaseAccess:
    def query(self, *_args, **_kwargs):
        raise AssertionError("Unauthorized principal reached database query")


@pytest.mark.parametrize(
    "principal, requested",
    [
        (SimpleNamespace(is_admin=True, is_platform_admin=True, school_id=None, role="admin"), None),
        (SimpleNamespace(is_admin=False, is_platform_admin=True, school_id=None, role="vortex_admin"), 7),
        (SimpleNamespace(is_admin=False, is_platform_admin=False, school_id=None, role="teacher"), None),
        (SimpleNamespace(is_admin=False, is_platform_admin=False, school_id=7, role="teacher"), 8),
    ],
)
def test_student_roster_rejects_platform_and_cross_school_access(principal, requested):
    with pytest.raises(HTTPException) as exc:
        list_students(school_id=requested, principal=principal, db=NoDatabaseAccess())
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "principal",
    [
        SimpleNamespace(is_admin=True, is_platform_admin=True, school_id=None, role="admin"),
        SimpleNamespace(is_admin=False, is_platform_admin=True, school_id=None, role="vortex_admin"),
        SimpleNamespace(is_admin=False, is_platform_admin=False, school_id=None, role="teacher"),
    ],
)
def test_student_detail_rejects_non_school_principals_before_database(principal):
    with pytest.raises(HTTPException) as exc:
        get_student(student_id=3, principal=principal, db=NoDatabaseAccess())
    assert exc.value.status_code == 403
