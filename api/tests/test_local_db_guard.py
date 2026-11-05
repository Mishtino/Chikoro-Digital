import unittest

from scripts.local_db_guard import validate_database_url


class LocalDatabaseGuardTests(unittest.TestCase):
    def test_accepts_only_documented_local_target(self):
        ok, _ = validate_database_url(
            "postgresql://chikoro_local:local_only_change_me@127.0.0.1:55432/chikoro_local"
        )
        self.assertTrue(ok)

    def test_rejects_missing_url(self):
        ok, _ = validate_database_url("")
        self.assertFalse(ok)

    def test_rejects_remote_host(self):
        ok, _ = validate_database_url(
            "postgresql://user:pass@db.example.com:55432/chikoro_local"
        )
        self.assertFalse(ok)

    def test_rejects_production_port(self):
        ok, _ = validate_database_url(
            "postgresql://user:pass@127.0.0.1:5432/chikoro_local"
        )
        self.assertFalse(ok)

    def test_rejects_wrong_database_name(self):
        ok, _ = validate_database_url(
            "postgresql://user:pass@127.0.0.1:55432/postgres"
        )
        self.assertFalse(ok)

    def test_rejects_non_postgres_scheme(self):
        ok, _ = validate_database_url("sqlite:///./chikoro.db")
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
