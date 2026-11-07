from app.routers.auth import _activation_failed_attempts


class ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class RecordingDB:
    def __init__(self, count):
        self.count = count
        self.calls = []

    def execute(self, statement, params):
        self.calls.append((str(statement), params))
        return ScalarResult(self.count)


def test_activation_rate_limit_locks_email_key_before_counting_failures():
    db = RecordingDB(4)

    count = _activation_failed_attempts(
        db,
        "guardian.activation.failed",
        "guardian_email_hash",
        "a" * 64,
    )

    assert count == 4
    assert len(db.calls) == 2
    lock_sql, lock_params = db.calls[0]
    count_sql, count_params = db.calls[1]
    assert "pg_advisory_xact_lock(hashtextextended" in lock_sql
    assert lock_params["lock_key"] == f"chikoro:guardian.activation.failed:{'a' * 64}"
    assert "created_at > now() - interval '1 hour'" in count_sql
    assert count_params == {
        "action": "guardian.activation.failed",
        "entity_type": "guardian_email_hash",
        "email_hash": "a" * 64,
    }


def test_activation_rate_limit_uses_separate_lock_keys_for_each_flow():
    db = RecordingDB(0)

    _activation_failed_attempts(
        db, "guardian.activation.failed", "guardian_email_hash", "b" * 64
    )
    _activation_failed_attempts(
        db, "student.activation.failed", "student_email_hash", "b" * 64
    )

    assert db.calls[0][1]["lock_key"] != db.calls[2][1]["lock_key"]
