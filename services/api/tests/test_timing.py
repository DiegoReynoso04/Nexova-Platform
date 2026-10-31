"""Middleware de timing (ticket de caching; app/core/timing.py).

Una línea por petición con método, path, status y ms; sin query string, que
puede llevar emails, y sin `GET /health` (D8). `REQUEST_TIMING_LOG=false` lo
quita. Ver docs/caching-analysis.md.
"""

import logging
import re
import unittest

from app.core.config import ConfigError, Settings
from app.core.timing import configure_timing_logger, logger

from .support import capture_logs, make_client

LINE = re.compile(r"^(GET|POST|PATCH|PUT|DELETE) (\S+) → (\d{3}) \| \d+\.\dms$")


def timing_lines(collector) -> list[str]:  # type: ignore[no-untyped-def]
    return [record.getMessage() for record in collector.records if record.name == "api.timing"]


class TimingMiddlewareTests(unittest.TestCase):
    def test_one_line_per_request_with_method_path_status_and_ms(self) -> None:
        client = make_client(authenticated=False)
        with capture_logs() as logs:
            client.get("/suppliers")
            client.post("/auth/login", data={"username": "nobody@example.invalid", "password": "wrong-password"})
        lines = timing_lines(logs)
        self.assertEqual(len(lines), 2)
        self.assertEqual(LINE.match(lines[0]).groups(), ("GET", "/suppliers", "401"))  # type: ignore[union-attr]
        self.assertEqual(LINE.match(lines[1]).groups(), ("POST", "/auth/login", "401"))  # type: ignore[union-attr]

    def test_health_is_not_logged(self) -> None:
        client = make_client(authenticated=False)
        with capture_logs() as logs:
            for _ in range(3):
                self.assertEqual(client.get("/health").status_code, 200)
        self.assertEqual(timing_lines(logs), [])

    def test_query_string_is_never_logged(self) -> None:
        client = make_client()
        email = "leak-check@example.invalid"
        with capture_logs() as logs:
            client.get("/auth/me", params={"email": email})
        lines = timing_lines(logs)
        self.assertEqual(len(lines), 1)
        self.assertEqual(LINE.match(lines[0]).groups(), ("GET", "/auth/me", "200"))  # type: ignore[union-attr]
        self.assertNotIn(email, logs.text())
        self.assertNotIn("?", lines[0])

    def test_logger_emits_info_and_gets_a_handler_only_once(self) -> None:
        handlers = list(logger.handlers)
        configure_timing_logger()
        configure_timing_logger()
        self.assertEqual(logger.handlers, handlers)
        self.assertEqual(logger.level, logging.INFO)


class TimingFlagTests(unittest.TestCase):
    def test_disabled_flag_removes_the_middleware(self) -> None:
        client = make_client(Settings(request_timing_log=False))
        with capture_logs() as logs:
            self.assertEqual(client.get("/auth/me").status_code, 200)
        self.assertEqual(timing_lines(logs), [])

    def test_from_env_defaults_to_enabled(self) -> None:
        self.assertTrue(Settings.from_env({}).request_timing_log)
        self.assertTrue(Settings.from_env({"REQUEST_TIMING_LOG": ""}).request_timing_log)

    def test_from_env_accepts_true_and_false_values(self) -> None:
        for raw in ("true", "TRUE", "1", "yes", "on", " true "):
            with self.subTest(raw=raw):
                self.assertTrue(Settings.from_env({"REQUEST_TIMING_LOG": raw}).request_timing_log)
        for raw in ("false", "False", "0", "no", "off"):
            with self.subTest(raw=raw):
                self.assertFalse(Settings.from_env({"REQUEST_TIMING_LOG": raw}).request_timing_log)

    def test_from_env_rejects_other_values(self) -> None:
        for raw in ("maybe", "2", "enabled"):
            with self.subTest(raw=raw), self.assertRaises(ConfigError):
                Settings.from_env({"REQUEST_TIMING_LOG": raw})


if __name__ == "__main__":
    unittest.main()
