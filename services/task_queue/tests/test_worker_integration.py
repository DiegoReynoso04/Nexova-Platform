"""Integración con Redis y PostgreSQL **locales** y un worker de verdad (subproceso, `prefork`).

Necesita `TASK_QUEUE_TEST_REDIS_URL` (Redis local; vacía las dos bases que usa) y
`TASK_QUEUE_TEST_DATABASE_URL` (PostgreSQL local cuya base termine en `_test`;
recrea `ops`). Sin las dos, se omite. Comprueba con las marcas de tiempo del log del
worker que ningún reintento sale antes de `base · 2^n`, que tras `max_retries=3`
la DLQ tiene `attempt=4` y `retries=3`, los fallos no reintentables y los dos
límites de tiempo, y que con la tabla sin migrar el fallo queda en el log.
"""

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from celery.result import AsyncResult
from job_runner.config import build_engine
from sqlalchemy import text

from task_queue import migrate
from task_queue.config import TaskQueueSettings
from task_queue.dead_letters import DeadLetterRepository
from task_queue.retries import backoff_floor

from .test_postgres_integration import check_test_database

REDIS_URL = os.environ.get("TASK_QUEUE_TEST_REDIS_URL", "").strip()
DATABASE_URL = os.environ.get("TASK_QUEUE_TEST_DATABASE_URL", "").strip()
SKIP = "TASK_QUEUE_TEST_REDIS_URL and TASK_QUEUE_TEST_DATABASE_URL are not set (local Redis and PostgreSQL only)"
SERVICES = Path(__file__).resolve().parents[2]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
LOG_LINE = re.compile(r"^\[(?P<ts>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}): (?P<level>\w+)/[^\]]+\] (?P<msg>.*)$")

ENGINE = None
WORKER = None
LOG_FILE = None
APP = None


def setUpModule():
    global ENGINE, WORKER, LOG_FILE, APP
    if not (REDIS_URL and DATABASE_URL):
        return
    if urlsplit(REDIS_URL).hostname not in LOCAL_HOSTS:
        raise RuntimeError("TASK_QUEUE_TEST_REDIS_URL must point to a local Redis")
    ENGINE = build_engine(check_test_database(DATABASE_URL).url)
    env = {**os.environ, "REDIS_URL": REDIS_URL, "DATABASE_URL": DATABASE_URL, "PYTHONPATH": str(SERVICES)}
    os.environ["REDIS_URL"] = REDIS_URL
    from task_queue.tests import integration_app

    APP = integration_app.app
    APP.connection_for_write().default_channel.client.flushdb()
    APP.backend.client.flushdb()
    LOG_FILE = tempfile.NamedTemporaryFile("w+", suffix=".log", delete=False, encoding="utf-8")
    WORKER = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "task_queue.tests.integration_app", "worker", "-P", "prefork", "-c", "1",
         "--loglevel=INFO", "--without-mingle", "--without-gossip", "-n", f"integration-{uuid.uuid4().hex[:6]}@%h"],
        cwd=SERVICES, env=env, stdout=LOG_FILE, stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if "ready." in Path(LOG_FILE.name).read_text(encoding="utf-8"):
            return
        if WORKER.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError("the integration worker did not start:\n" + Path(LOG_FILE.name).read_text(encoding="utf-8")[-3000:])


def tearDownModule():
    if WORKER is not None:
        WORKER.send_signal(signal.SIGTERM)
        try:
            WORKER.wait(timeout=30)
        except subprocess.TimeoutExpired:
            WORKER.kill()
    if ENGINE is not None:
        ENGINE.dispose()
    if LOG_FILE is not None:
        if os.environ.get("TASK_QUEUE_KEEP_WORKER_LOG"):
            print(f"\nworker log: {LOG_FILE.name}", file=sys.stderr)
        else:
            LOG_FILE.close()
            os.unlink(LOG_FILE.name)


def worker_lines(task_id: str) -> list[tuple[datetime, str]]:
    lines = []
    for raw in Path(LOG_FILE.name).read_text(encoding="utf-8").splitlines():
        match = LOG_LINE.match(raw)
        if match and task_id in match["msg"]:
            lines.append((datetime.strptime(match["ts"], "%Y-%m-%d %H:%M:%S,%f"), match["msg"]))
    return lines


def ours(task_id: str) -> list[tuple[datetime, str]]:
    return [(ts, msg) for ts, msg in worker_lines(task_id) if msg.startswith(f"task_id={task_id}")]


def field(message: str, name: str) -> str:
    match = re.search(rf'{name}=("(?:[^"\\]|\\.)*"|\S+)', message)
    return match[1].strip('"') if match else ""


def wait_ready(result: AsyncResult, timeout: float) -> AsyncResult:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not result.ready():
        time.sleep(0.3)
    return result


def wait_for(predicate, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.3)
    return predicate()


@unittest.skipUnless(REDIS_URL and DATABASE_URL, SKIP)
class WorkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        with ENGINE.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS ops CASCADE"))
        migrate.migrate(ENGINE, dry_run=False)
        self.repo = DeadLetterRepository(ENGINE)

    def send(self, name: str) -> AsyncResult:
        return APP.send_task(name, kwargs={"token": uuid.uuid4().hex})

    def row(self, task_id: str):
        return next((row for row in self.repo.list() if str(row["task_id"]) == task_id), None)

    def assert_no_secret(self, text_value: str):
        for secret in (urlsplit(DATABASE_URL).password, urlsplit(REDIS_URL).password, DATABASE_URL, REDIS_URL):
            if secret:
                self.assertNotIn(secret, text_value)

    def test_success(self):
        result = wait_ready(self.send("integration.succeed"), 20)
        self.assertEqual(result.state, "SUCCESS")
        statuses = [field(msg, "status") for _, msg in ours(result.id)]
        self.assertEqual(statuses, ["started", "success"])
        self.assertIsNone(self.row(result.id))

    def test_retries_wait_at_least_the_floor_and_end_in_the_dlq(self):
        result = wait_ready(self.send("integration.always_transient"), 60)
        self.assertEqual(result.state, "FAILURE")
        lines = ours(result.id)
        statuses = [field(msg, "status") for _, msg in lines]
        self.assertEqual(
            statuses, ["started", "retry", "started", "retry", "started", "retry", "started", "dead_letter", "dead_letter_stored"]
        )
        retry_lines = [(ts, msg) for ts, msg in lines if field(msg, "status") == "retry"]
        started = [ts for ts, msg in lines if field(msg, "status") == "started"]
        for n, ((retried_at, msg), next_start) in enumerate(zip(retry_lines, started[1:], strict=True)):
            gap = (next_start - retried_at).total_seconds()
            countdown = float(field(msg, "countdown_s"))
            with self.subTest(retry=n + 1, gap=gap, countdown=countdown):
                self.assertGreaterEqual(countdown, backoff_floor(n))
                self.assertGreaterEqual(gap, backoff_floor(n))
                self.assertGreaterEqual(gap, countdown - 0.05)
        self.assertEqual([field(msg, "attempt") for _, msg in lines if field(msg, "status") == "started"], ["1/4", "2/4", "3/4", "4/4"])
        row = wait_for(lambda: self.row(result.id), 10)
        self.assertEqual((row["attempt"], row["retries"], row["max_retries"], row["reason"]), (4, 3, 3, "retries_exhausted"))
        self.assertEqual(row["error_message"], "OperationalError (Exception)")
        self.assertEqual(set(row["task_kwargs"]), {"token"})
        self.assertEqual(type(result.result).__name__, "TaskFailedError")
        self.assert_no_secret(Path(LOG_FILE.name).read_text(encoding="utf-8") + repr(result.result))

    def test_transient_then_success(self):
        result = wait_ready(self.send("integration.transient_twice"), 40)
        self.assertEqual((result.state, result.result), ("SUCCESS", "recovered"))
        self.assertIsNone(self.row(result.id))

    def test_non_retryable_goes_straight_to_the_dlq(self):
        result = wait_ready(self.send("integration.non_retryable"), 20)
        self.assertEqual(result.state, "FAILURE")
        self.assertEqual([field(msg, "status") for _, msg in ours(result.id)], ["started", "dead_letter", "dead_letter_stored"])
        row = wait_for(lambda: self.row(result.id), 10)
        self.assertEqual((row["attempt"], row["retries"], row["reason"]), (1, 0, "non_retryable"))
        self.assertTrue(row["error_message"].startswith("ValueError: invalid token "))
        self.assert_no_secret(row["error_message"])

    def test_soft_time_limit(self):
        result = wait_ready(self.send("integration.soft_timeout"), 30)
        self.assertEqual(result.state, "FAILURE")
        row = wait_for(lambda: self.row(result.id), 10)
        self.assertEqual((row["attempt"], row["reason"], row["error_class"]), (1, "time_limit", "SoftTimeLimitExceeded"))

    def test_hard_time_limit_is_recorded_by_the_worker_process(self):
        result = wait_ready(self.send("integration.hard_timeout"), 30)
        self.assertEqual(result.state, "FAILURE")
        row = wait_for(lambda: self.row(result.id), 15)
        self.assertEqual((row["attempt"], row["retries"], row["reason"], row["error_class"]), (1, 0, "time_limit", "TimeLimitExceeded"))

    def test_unmigrated_table_leaves_the_failure_in_the_log(self):
        with ENGINE.begin() as connection:
            connection.execute(text("DROP SCHEMA ops CASCADE"))
        result = wait_ready(self.send("integration.non_retryable"), 20)
        self.assertEqual(result.state, "FAILURE")
        line = wait_for(lambda: [msg for _, msg in ours(result.id) if field(msg, "status") == "dead_letter_not_stored"], 10)
        self.assertEqual(len(line), 1)
        self.assertEqual(field(line[0], "cause"), "ProgrammingError")
        self.assertEqual(field(line[0], "reason"), "non_retryable")
        self.assertIn("attempt=1/4", line[0])


if __name__ == "__main__":
    unittest.main()
