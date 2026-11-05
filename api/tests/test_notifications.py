from uuid import uuid4

from app.deps_supabase import SupabasePrincipal, get_supabase_principal
from app.main import app
from app.models.notification import Notification
from app.models.school import School


def test_process_does_not_mark_queued_notifications_as_sent_without_delivery_provider(
    client, db_session
):
    school = School(code="NT001", name="Notification Delivery Test")
    db_session.add(school)
    db_session.flush()
    notification = Notification(
        school_id=school.id,
        dedupe_key="notification-delivery-not-configured",
        channel="email",
        recipient="guardian@example.test",
        payload={"subject": "Test"},
        status="queued",
        attempts=0,
    )
    db_session.add(notification)
    db_session.commit()

    principal = SupabasePrincipal(
        auth_user_id=uuid4(),
        user_id=1,
        school_id=school.id,
        role="owner",
        is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.post("/notifications/process")

    assert response.status_code == 501
    assert "delivery is not configured" in response.json()["detail"].lower()
    db_session.refresh(notification)
    assert notification.status == "queued"
    assert notification.attempts == 0
    assert notification.sent_at is None

def test_school_user_cannot_filter_notifications_by_another_school(client, db_session):
    own = School(code="NT002", name="Own Notification School")
    other = School(code="NT003", name="Other Notification School")
    db_session.add_all([own, other])
    db_session.commit()
    principal = SupabasePrincipal(
        auth_user_id=uuid4(), user_id=2, school_id=own.id,
        role="owner", is_admin=False,
    )
    app.dependency_overrides[get_supabase_principal] = lambda: principal

    response = client.get(f"/notifications?school_id={other.id}")

    assert response.status_code == 403

