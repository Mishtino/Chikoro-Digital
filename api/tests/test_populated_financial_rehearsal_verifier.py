"""Regression checks for the populated-finance refusal verifier (no real DB)."""
import importlib
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import local_db_guard

with patch.dict(sys.modules, {"local_db_guard": local_db_guard}):
    verifier = importlib.import_module("scripts.verify_populated_financial_rehearsal")

URL = "postgresql://chikoro_local:local_only_change_me@127.0.0.1:55432/chikoro_local"


class PopulatedRehearsalVerifierTests(unittest.TestCase):
    def test_rejects_unsafe_target_without_connecting(self):
        with patch.dict("os.environ", {
            "DATABASE_URL": "postgresql://user:pass@remote.example.com/prod",
            "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True), patch.object(verifier.psycopg, "connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "Unsafe verification target"):
                verifier.main()
            connect.assert_not_called()

    def test_rejects_missing_opt_in_without_connecting(self):
        with patch.dict("os.environ", {"DATABASE_URL": URL}, clear=True), \
             patch.object(verifier.psycopg, "connect") as connect:
            with self.assertRaisesRegex(RuntimeError, "opt-in required"):
                verifier.main()
            connect.assert_not_called()

    def test_detects_modified_values_even_when_row_counts_match(self):
        snapshots = [
            [[(1, "School One")], [(1, 100)], [(1, 20)], [(1, 10)]],
            [[(1, "School One")], [(1, 999)], [(1, 20)], [(1, 10)]],
        ]
        connections = []
        for snapshot in snapshots:
            db = MagicMock()
            db.execute.return_value.fetchall.side_effect = snapshot
            cm = MagicMock()
            cm.__enter__.return_value = db
            connections.append(cm)
        refusal = SimpleNamespace(returncode=1, stderr="Refusing rehearsal: public schema is not empty")
        with patch.dict("os.environ", {
            "DATABASE_URL": URL, "CHIKORO_REHEARSAL_EMPTY_DATABASE": "yes",
        }, clear=True), \
             patch.object(verifier.psycopg, "connect", side_effect=connections), \
             patch.object(verifier.subprocess, "run", return_value=refusal) as run:
            with self.assertRaisesRegex(AssertionError, "changed financial fixture rows"):
                verifier.main()
            run.assert_called_once()
        for cm in connections:
            db = cm.__enter__.return_value
            self.assertEqual(db.execute.call_count, 5)
            for call in db.execute.call_args_list[1:]:
                self.assertIn("ORDER BY id", call.args[0])


if __name__ == "__main__":
    unittest.main()
