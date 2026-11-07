import unittest
from unittest.mock import patch, Mock

from scripts import local_db_guard

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

    def test_rejects_query_parameters_that_could_override_connection_target(self):
        ok, _ = validate_database_url(
            "postgresql://user:pass@127.0.0.1:55432/chikoro_local?host=db.example.com"
        )
        self.assertFalse(ok)

    def test_rejects_url_fragments(self):
        ok, _ = validate_database_url(
            "postgresql://user:pass@127.0.0.1:55432/chikoro_local#remote"
        )
        self.assertFalse(ok)


    def test_rejects_other_loopback_host_and_invalid_port(self):
        for url in (
            "postgresql://user:pass@127.0.0.2:55432/chikoro_local",
            "postgresql://user:pass@127.0.0.1:not-a-port/chikoro_local",
            "postgresql://user:pass@127.0.0.1:55432/chikoro_local?hostaddr=10.0.0.2",
            "postgresql://user:pass@127.0.0.1:55432/chikoro_local?service=prod",
        ):
            with self.subTest(url=url):
                self.assertFalse(validate_database_url(url)[0])

    def test_does_not_launch_command_for_unsafe_database(self):
        with patch.dict("os.environ", {"DATABASE_URL": "postgresql://user:pass@prod.example.com:5432/prod"}):
            with patch.object(local_db_guard.subprocess, "run") as run:
                self.assertEqual(local_db_guard.main(["--", "alembic", "upgrade", "head"]), 2)
                run.assert_not_called()

    def test_runs_local_command_and_propagates_exit_code(self):
        local_url = "postgresql://user:pass@127.0.0.1:55432/chikoro_local"
        with patch.dict("os.environ", {"DATABASE_URL": local_url}):
            with patch.object(local_db_guard.subprocess, "run", return_value=Mock(returncode=7)) as run:
                self.assertEqual(local_db_guard.main(["--", "alembic", "upgrade", "head"]), 7)
                run.assert_called_once_with(["alembic", "upgrade", "head"], check=False)

    def test_does_not_launch_without_command(self):
        with patch.object(local_db_guard.subprocess, "run") as run:
            self.assertEqual(local_db_guard.main(["--"]), 2)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
