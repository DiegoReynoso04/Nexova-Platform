import unittest

from sqlalchemy.exc import OperationalError

from job_runner.redact import REDACTED, REDACTED_URL, describe_exception, redact

URL = "postgresql://nexova_app:s3cretPass@db.internal.example:6543/postgres"


class RedactTests(unittest.TestCase):
    def test_urls_with_a_scheme_are_removed(self):
        self.assertEqual(redact("failed: https://api.example.com/x?token=1 end", environ={}), f"failed: {REDACTED_URL} end")
        self.assertNotIn("nexova_app", redact(f"connect {URL}", environ={}))

    def test_secret_variables_and_the_database_password_are_removed(self):
        environ = {"DATABASE_URL": URL, "TELEMETRY_SUPPLIER_KEY": "k" * 40, "JWT_SECRET_KEY": "short"}
        text = redact(f"pw s3cretPass key {'k' * 40} jwt short", environ=environ)
        self.assertNotIn("s3cretPass", text)
        self.assertNotIn("k" * 40, text)
        self.assertNotIn("short", text)
        self.assertIn(REDACTED, text)

    def test_very_short_values_are_not_treated_as_secrets(self):
        self.assertEqual(redact("a 1 b", environ={"DATABASE_URL": "1"}), "a 1 b")

    def test_extra_secrets(self):
        self.assertNotIn("hunter22", redact("x hunter22", environ={}, extra=["hunter22"]))

    def test_describe_exception_keeps_class_and_message(self):
        self.assertEqual(describe_exception(ValueError("bad  input"), environ={}), "ValueError: bad input")
        self.assertEqual(describe_exception(KeyboardInterrupt(), environ={}), "KeyboardInterrupt")

    def test_describe_exception_truncates_to_500_characters(self):
        self.assertEqual(len(describe_exception(RuntimeError("x" * 2000), environ={})), 500)

    def test_describe_exception_for_sqlalchemy_is_only_the_classes(self):
        error = OperationalError("SELECT 1", {"p": "s3cretPass"}, Exception(f"connection to {URL} failed"))
        text = describe_exception(error, environ={})
        self.assertEqual(text, "OperationalError (Exception)")

    def test_describe_exception_redacts_urls_in_other_errors(self):
        text = describe_exception(RuntimeError(f"cannot reach {URL}"), environ={"DATABASE_URL": URL})
        self.assertNotIn("s3cretPass", text)
        self.assertNotIn("db.internal.example", text)
