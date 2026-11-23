"""Fail-closed checks must run before the financial rehearsal opens a DB connection.

These tests never connect to PostgreSQL or execute migrations.
"""
import importlib
import sys
import unittest
from unittest.mock import patch

from scripts import local_db_guard

# The CLI script uses a sibling import when invoked as python scripts/...
with patch.dict(sys.modules, {"local_db_guard": local_db_guard}):
    rehearse_financial_migration = importlib.import_module("scripts.rehearse_financial_migration")


LOCAL_URL = "postgresql://user:pass@127.0.0.1:55432/chikoro_local"


class FinancialRehearsalPreconnectTests(unittest.TestCase):
    def test_rejects_remote_database_even_with_opt_in(self):
        remote = "postgresql://user:pass@db.example.com:5432/production"
        with patch.dict("os.environ", {
            "DATABASE_URL": remote,
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True):
            with patch.object(rehearse_financial_migration.psycopg, "connect") as connect:
                with self.assertRaisesRegex(RuntimeError, "Unsafe PostgreSQL rehearsal target"):
                    rehearse_financial_migration.run()
                connect.assert_not_called()

    def test_rejects_missing_explicit_empty_database_opt_in(self):
        for value in (None, "", "YES", "true", "1"):
            with self.subTest(value=value):
                env = {"DATABASE_URL": LOCAL_URL}
                if value is not None:
                    env["CHIKORO_REHEARSAL_EMPTY_DATABASE"] = value
                with patch.dict("os.environ", env, clear=True):
                    with patch.object(rehearse_financial_migration.psycopg, "connect") as connect:
                        with self.assertRaisesRegex(RuntimeError, "CHIKORO_REHEARSAL_EMPTY_DATABASE=yes"):
                            rehearse_financial_migration.run()
                        connect.assert_not_called()

    def test_rejects_nonempty_public_schema_before_loading_sql(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (1,)
        connection = MagicMock()
        connection.__enter__.return_value = db

        with patch.dict("os.environ", {
            "DATABASE_URL": LOCAL_URL,
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True):
            with patch.object(rehearse_financial_migration.psycopg, "connect", return_value=connection) as connect:
                with patch.object(type(rehearse_financial_migration.SCHEMA), "read_text") as sql_read:
                    with self.assertRaisesRegex(RuntimeError, "public schema is not empty"):
                        rehearse_financial_migration.run()
                    sql_read.assert_not_called()
                connect.assert_called_once_with(LOCAL_URL, autocommit=True)
                db.execute.assert_called_once()
                assert "pg_class" in db.execute.call_args.args[0]
                self.assertIn("'S'", db.execute.call_args.args[0], "Sequences must block rehearsal")

    def test_rejects_function_only_public_schema_before_loading_sql(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [(0,), (1,)]
        connection = MagicMock()
        connection.__enter__.return_value = db

        with patch.dict("os.environ", {
            "DATABASE_URL": LOCAL_URL,
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True):
            with patch.object(rehearse_financial_migration.psycopg, "connect", return_value=connection):
                with patch.object(type(rehearse_financial_migration.SCHEMA), "read_text") as sql_read:
                    with self.assertRaisesRegex(RuntimeError, "public schema contains functions"):
                        rehearse_financial_migration.run()
                    sql_read.assert_not_called()
        self.assertEqual(db.execute.call_count, 2)
        self.assertIn("pg_class", db.execute.call_args_list[0].args[0])
        self.assertIn("pg_proc", db.execute.call_args_list[1].args[0])


    def test_rejects_standalone_public_types_before_loading_sql(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [(0,), (0,), (1,)]
        connection = MagicMock()
        connection.__enter__.return_value = db

        with patch.dict("os.environ", {
            "DATABASE_URL": LOCAL_URL,
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True):
            with patch.object(rehearse_financial_migration.psycopg, "connect", return_value=connection):
                with patch.object(type(rehearse_financial_migration.SCHEMA), "read_text") as sql_read:
                    with self.assertRaisesRegex(RuntimeError, "public schema contains standalone types"):
                        rehearse_financial_migration.run()
                    sql_read.assert_not_called()
        self.assertEqual(db.execute.call_count, 3)
        self.assertIn("pg_type", db.execute.call_args_list[2].args[0])
        self.assertIn("'e', 'd', 'r', 'm'", db.execute.call_args_list[2].args[0])

    def test_rejects_public_extensions_before_loading_sql(self):
        from unittest.mock import MagicMock

        db = MagicMock()
        db.execute.return_value.fetchone.side_effect = [(0,), (0,), (0,), (1,)]
        connection = MagicMock()
        connection.__enter__.return_value = db

        with patch.dict("os.environ", {
            "DATABASE_URL": LOCAL_URL,
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True):
            with patch.object(rehearse_financial_migration.psycopg, "connect", return_value=connection):
                with patch.object(type(rehearse_financial_migration.SCHEMA), "read_text") as sql_read:
                    with self.assertRaisesRegex(RuntimeError, "public schema contains extensions"):
                        rehearse_financial_migration.run()
                    sql_read.assert_not_called()
        self.assertEqual(db.execute.call_count, 4)
        self.assertIn("pg_extension", db.execute.call_args_list[3].args[0])


if __name__ == "__main__":
    unittest.main()
