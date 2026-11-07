from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.paynow import PaynowAttempt
from app.models.school import School
from app.routers import paynow
from app.services.crypto import encrypt


def test_paynow_rejects_empty_invoice_selection_before_provider_call(client, db_session, monkeypatch):
    school = School(
        code="PN-EMPTY", name="Empty Selection School",
        paynow_integration_id="test-integration",
        paynow_integration_key=encrypt("test-integration-key"),
    )
    db_session.add(school)
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=1, school_id=school.id,
        role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    def unexpected_provider_call(**kwargs):
        raise AssertionError("Provider must not be called for an empty invoice selection")

    monkeypatch.setattr(paynow, "initiate_transaction", unexpected_provider_call)
    response = client.post(
        "/paynow/initiate",
        json={"school_id": school.id, "invoice_ids": []},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Paynow checkout currently supports one invoice at a time"
    assert db_session.query(PaynowAttempt).count() == 0
