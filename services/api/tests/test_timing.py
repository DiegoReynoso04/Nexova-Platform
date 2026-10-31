"""Middleware de timing (ticket de caching, F0; app/core/timing.py).

Una línea por petición con método, path, status y ms; sin query string, que
puede llevar emails. Ver docs/caching-analysis.md.
"""

import logging
import re
import unittest

from app.core.timing import configure_timing_logger, logger

from .support import capture_logs, make_client

LINE = re.compile(r"^(GET|POST|PATCH|PUT|DELETE) (\S+) → (\d{3}) \| \d+\.\dms$")


def timing_lines(collector) -> list[str]:  # type: ignore[no-untyped-def]
    return [record.getMessage() for record in collector.records if record.name == "api.timing"]


class TimingMiddlewareTests(unittest.TestCase):
    def test_one_line_per_request_with_method_path_status_and_ms(self) -> None:
        client = make_client(authenticated=False)
        with capture_logs() as logs:
            client.get("/health")
            client.get("/suppliers")
        lines = timing_lines(logs)
        self.assertEqual(len(lines), 2)
        self.assertEqual(LINE.match(lines[0]).groups(), ("GET", "/health", "200"))  # type: ignore[union-attr]
        self.assertEqual(LINE.match(lines[1]).groups(), ("GET", "/suppliers", "401"))  # type: ignore[union-attr]

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


if __name__ == "__main__":
    unittest.main()
