"""Regression tests for school-scoped invoice listing authorization."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers.payments import _sid, list_invoices


class NoDatabaseAccess:
    def query(self, *_args, **_kwargs):
        raise AssertionError("Unauthorized identity must not reach the database")


@pytest.mark.parametrize(
    "principal, requested",
    [
        (SimpleNamespace(is_admin=True, school_id=None), None),
        (SimpleNamespace(is_admin=True, school_id=1), 1),
        (SimpleNamespace(is_admin=False, school_id=None), None),
        (SimpleNamespace(is_admin=False, school_id=1), 2),
    ],
)
def test_invoice_listing_rejects_platform_or_cross_school_identity(principal, requested):
    with pytest.raises(HTTPException) as exc:
        list_invoices(student_id=None, school_id=requested, principal=principal, db=NoDatabaseAccess())
    assert exc.value.status_code == 403


def test_school_scope_accepts_own_school_without_explicit_school_id():
    principal = SimpleNamespace(is_admin=False, school_id=7)
    assert _sid(principal, None) == 7
    assert _sid(principal, 7) == 7
