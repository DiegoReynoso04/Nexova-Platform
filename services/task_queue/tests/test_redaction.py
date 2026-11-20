"""El mensaje de error completo, sin secretos (A12)."""

import logging
import unittest

from sqlalchemy.exc import OperationalError

from task_queue.config import ERROR_MESSAGE_MAX_CHARS
from task_queue.redaction import RedactingFilter, describe_failure, queue_secrets, redact_text

ENV = {
    "DATABASE_URL": "postgresql://nexova:db-Secret-123@db.example.invalid:6543/postgres",
    "REDIS_URL": "redis://:redis-Secret-456@redis:6379/0",
    "REDIS_PASSWORD": "redis-Secret-456",
    "FLOWER_BASIC_AUTH": "flower:flower-Secret-789",
    "JWT_SECRET_KEY": "jwt-Secret-abcdefghijklmnopqrstuvwxyz",
}
SECRETS = ("db-Secret-123", "redis-Secret-456", "flower-Secret-789", "jwt-Secret-abc", "db.example.invalid")


class DescribeFailureTests(unittest.TestCase):
    def assertClean(self, text):
        for secret in SECRETS:
            self.assertNotIn(secret, text)

    def test_sqlalchemy_errors_keep_only_the_classes(self):
        error = OperationalError("SELECT * FROM telemetry_events", {"p": 1}, ValueError(f"could not connect to {ENV['DATABASE_URL']}"))
        error_class, message = describe_failure(error, ENV)
        self.assertEqual((error_class, message), ("OperationalError", "OperationalError (ValueError)"))

    def test_other_errors_keep_the_message_redacted(self):
        error = RuntimeError(f"broker {ENV['REDIS_URL']} refused; password redis-Secret-456; auth {ENV['FLOWER_BASIC_AUTH']}")
        error_class, message = describe_failure(error, ENV)
        self.assertEqual(error_class, "RuntimeError")
        # REDIS_URL entera es un valor secreto: sale como <redacted> (antes de la regla de URL).
        self.assertEqual(message, "RuntimeError: broker <redacted> refused; password <redacted>; auth <redacted>")
        self.assertClean(message)

    def test_an_unknown_url_is_redacted_as_a_url(self):
        _, message = describe_failure(RuntimeError("timeout calling https://user:pw@api.example.invalid/x"), ENV)
        self.assertEqual(message, "RuntimeError: timeout calling <redacted-url>")

    def test_whitespace_is_collapsed_and_the_message_truncated(self):
        _, message = describe_failure(ValueError("a\n\n  b " + "x" * 5000), ENV)
        self.assertTrue(message.startswith("ValueError: a b x"))
        self.assertEqual(len(message), ERROR_MESSAGE_MAX_CHARS)

    def test_empty_message(self):
        self.assertEqual(describe_failure(KeyError(), ENV), ("KeyError", "KeyError"))

    def test_queue_secrets(self):
        secrets = queue_secrets(ENV)
        for value in ("redis-Secret-456", "flower-Secret-789", "flower:flower-Secret-789", ENV["REDIS_URL"]):
            self.assertIn(value, secrets)
        self.assertEqual(queue_secrets({"REDIS_PASSWORD": "abc"}), [])  # demasiado corto


class RedactingFilterTests(unittest.TestCase):
    def test_message_args_and_traceback_are_redacted(self):
        try:
            raise RuntimeError(f"could not reach {ENV['REDIS_URL']}")
        except RuntimeError as error:
            record = logging.LogRecord("celery.app.trace", logging.ERROR, __file__, 1, "Task %s raised: %r", ("x", error), exc_info=(type(error), error, error.__traceback__))
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, ENV):
            self.assertTrue(RedactingFilter().filter(record))
            formatted = logging.Formatter().format(record)
            self.assertIn("could not reach <redacted>", formatted)
            self.assertIn("Traceback", formatted)
            for secret in SECRETS:
                self.assertNotIn(secret, formatted)
            self.assertIsNone(record.args)

    def test_redact_text_uses_the_environment(self):
        self.assertEqual(redact_text("pw redis-Secret-456", ENV), "pw <redacted>")


if __name__ == "__main__":
    unittest.main()
