"""`readonly.py` (fotos y cuadre de la demo, siempre en solo lectura) y `secret.py` (el block del worker)."""

import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from business_performance import readonly, secret
from business_performance.config import target_from_url

REPORTING_DOCS = Path(__file__).resolve().parents[3] / "docs" / "reporting"
FAKE_LOCAL = "postgresql://fake_user:fake-password-123@127.0.0.1:55432/nexova_test"


class StatementSplitTests(unittest.TestCase):
    def test_skips_psql_meta_commands_and_comments(self):
        sql = "\\set ON_ERROR_STOP on\n-- a comment\nSELECT 1;\n\nSELECT 'a;b'\nFROM x;\nSELECT 3"
        self.assertEqual(readonly.statements(sql), ["SELECT 1", "SELECT 'a;b'\nFROM x", "SELECT 3"])

    def test_the_review_sql_files_split_into_selects_only(self):
        for name in ("pipeline-check.sql", "demo-snapshot.sql", "demo-reporting-access.sql"):
            with self.subTest(file=name):
                parts = readonly.statements((REPORTING_DOCS / name).read_text(encoding="utf-8"))
                self.assertGreater(len(parts), 0)
                for part in parts:
                    self.assertRegex(part.lstrip().upper(), r"^(SELECT|WITH)\b")


class ReadOnlyTransactionTests(unittest.TestCase):
    def test_read_only_first_and_always_rolled_back(self):
        connection = mock.MagicMock()
        transaction = connection.begin.return_value
        engine = mock.MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        result = connection.execute.return_value
        result.returns_rows = True
        result.keys.return_value = ["n"]
        result.all.return_value = [(1,)]
        outputs = readonly.run_readonly(engine, ["SELECT 1 AS n"])
        first = connection.execute.call_args_list[0].args[0]
        self.assertEqual(str(first), "SET TRANSACTION READ ONLY")
        transaction.rollback.assert_called_once()
        transaction.commit.assert_not_called()
        self.assertIn("(1 fila)", outputs[0])

    def test_rolled_back_even_if_a_statement_fails(self):
        connection = mock.MagicMock()
        transaction = connection.begin.return_value
        engine = mock.MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        connection.execute.side_effect = [None, RuntimeError("boom")]
        with self.assertRaises(RuntimeError):
            readonly.run_readonly(engine, ["SELECT 1"])
        transaction.rollback.assert_called_once()

    def test_cli_prints_only_the_host(self):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(readonly, "run_readonly", return_value=["t"]), \
                mock.patch.object(readonly, "build_engine"), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = readonly.run([str(REPORTING_DOCS / "demo-snapshot.sql")],
                                target=target_from_url(FAKE_LOCAL, "entorno"))
        self.assertEqual(code, 0)
        self.assertIn("host 127.0.0.1 (solo lectura", out.getvalue())
        self.assertNotIn("fake-password-123", out.getvalue() + err.getvalue())


class SecretTests(unittest.TestCase):
    def test_requires_the_prefect_server(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": FAKE_LOCAL}, clear=False):
            os.environ.pop("PREFECT_API_URL", None)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(secret.main(), 2)

    def test_saves_the_resolved_url_and_prints_only_the_host(self):
        saved = {}

        class FakeSecret:
            def __init__(self, value):
                saved["value"] = value

            def save(self, name, overwrite):
                saved["name"], saved["overwrite"] = name, overwrite

        out = io.StringIO()
        with mock.patch.dict(os.environ, {"DATABASE_URL": FAKE_LOCAL, "PREFECT_API_URL": "http://prefect.invalid/api"}), \
                mock.patch("prefect.blocks.system.Secret", FakeSecret), contextlib.redirect_stdout(out):
            self.assertEqual(secret.main(), 0)
        self.assertEqual(saved, {"value": "postgresql+psycopg2://fake_user:fake-password-123@127.0.0.1:55432/nexova_test",
                                 "name": "nexova-supabase-database-url", "overwrite": True})
        self.assertIn("host 127.0.0.1", out.getvalue())
        self.assertNotIn("fake-password-123", out.getvalue())


if __name__ == "__main__":
    unittest.main()
