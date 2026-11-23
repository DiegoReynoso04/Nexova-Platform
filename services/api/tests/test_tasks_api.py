"""`GET /tasks/{task_id}` (DEV-55, A10; SPECS Parte J) y la configuración de la cola en la API.

Con el cliente real de `task_queue` y dobles en memoria (`task_queue_support`): un
backend que retiene las tareas (`hold=True`) para recorrer cada estado de la cola.
"""

import unittest
import uuid
from typing import Any

from redis.exceptions import ConnectionError as RedisDown

from app.auth.models import UserRole
from app.core.config import ConfigError, Settings
from app.modules.tasks.dependencies import build_task_queue

from .support import authorize
from .task_queue_support import install_task_queue
from .telemetry_support import storage_client

REPORT = {
    "period": {"from": "2026-11-01T00:00:00.000Z", "to": "2026-11-02T00:00:00.000Z"},
    "metrics": {
        "events_per_day": [{"day": "2026-11-01", "service": "backoffice", "events": 0}],
        "error_rate_by_type": [],
        "page_load_latency_by_route": [],
        "dominant_event_types": [],
        "auth_failure_rate": [],
    },
}


class TasksCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = storage_client(authenticated=True)
        self.addCleanup(self.client.auth_dir.cleanup)  # type: ignore[attr-defined]
        self.app = self.client.app
        self.queue, self.store, self.backend = install_task_queue(self.app, self.app.state.inventory_engine, hold=True)  # type: ignore[attr-defined]

    def enqueue(self) -> str:
        response = self.client.get("/telemetry/report", params={"start_date": "2026-11-01", "end_date": "2026-11-02"})
        self.assertEqual(response.status_code, 202, response.text)
        task_id: str = response.json()["task_id"]
        return task_id

    def get(self, task_id: str) -> Any:
        return self.client.get(f"/tasks/{task_id}")


class StatusTests(TasksCase):
    def test_each_celery_state_maps_to_the_four_of_the_contract(self) -> None:
        cases = {
            "PENDING": "pending",
            "RECEIVED": "pending",
            "STARTED": "started",
            "RETRY": "started",  # monótono: no vuelve a pending entre reintentos
            "SUCCESS": "success",
            "FAILURE": "failure",
            "REVOKED": "failure",
        }
        task_id = self.enqueue()
        for state, expected in cases.items():
            with self.subTest(state=state):
                self.backend.set_state(task_id, state, REPORT if state == "SUCCESS" else None)
                response = self.get(task_id)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], expected)

    def test_result_is_null_until_the_task_ends(self) -> None:
        task_id = self.enqueue()
        for state in ("PENDING", "STARTED", "RETRY"):
            with self.subTest(state=state):
                self.backend.set_state(task_id, state)
                self.assertIsNone(self.get(task_id).json()["result"])

    def test_success_returns_the_report_with_its_schema(self) -> None:
        task_id = self.enqueue()
        self.backend.set_state(task_id, "SUCCESS", REPORT)
        self.assertEqual(self.get(task_id).json(), {"task_id": task_id, "status": "success", "result": REPORT})

    def test_failure_returns_a_fixed_object_without_the_error(self) -> None:
        task_id = self.enqueue()
        self.backend.set_state(task_id, "FAILURE", RuntimeError("could not connect to postgresql://u:secret@db:5432/x"))
        response = self.get(task_id)
        self.assertEqual(response.json(), {"task_id": task_id, "status": "failure", "result": {"code": "task_failed", "detail": "the task failed"}})
        self.assertNotIn("secret", response.text)

    def test_no_store(self) -> None:
        self.assertEqual(self.get(self.enqueue()).headers["cache-control"], "no-store")

    def test_a_just_enqueued_task_is_already_visible(self) -> None:
        task_id = self.enqueue()
        self.assertEqual(self.get(task_id).json(), {"task_id": task_id, "status": "pending", "result": None})


class NotFoundTests(TasksCase):
    def assert_not_found(self, task_id: str) -> None:
        response = self.get(task_id)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "task not found", "code": "task_not_found"})

    def test_an_invented_id_is_404_even_though_the_queue_would_say_pending(self) -> None:
        self.assert_not_found(str(uuid.uuid4()))

    def test_a_malformed_id_is_404(self) -> None:
        for value in ("no-es-un-uuid", "123", "' OR 1=1 --"):
            with self.subTest(value=value):
                self.assert_not_found(value)

    def test_another_users_task_is_404_not_403(self) -> None:
        task_id = self.enqueue()
        authorize(self.client, UserRole.USER)
        self.assert_not_found(task_id)

    def test_an_admin_sees_any_task(self) -> None:
        task_id = self.enqueue()
        authorize(self.client, UserRole.ADMIN)
        self.assertEqual(self.get(task_id).status_code, 200)

    def test_an_expired_task_is_404(self) -> None:
        task_id = self.enqueue()
        self.store.delete(f"nexova:task:{task_id}")
        self.assert_not_found(task_id)


class AvailabilityTests(TasksCase):
    def test_without_token_is_401(self) -> None:
        task_id = self.enqueue()
        del self.client.headers["Authorization"]
        self.assertEqual(self.get(task_id).status_code, 401)

    def test_without_a_task_queue_is_503(self) -> None:
        self.app.state.task_queue = None  # type: ignore[attr-defined]
        response = self.get(str(uuid.uuid4()))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "task_queue_unavailable")

    def test_redis_down_is_503_without_details(self) -> None:
        task_id = self.enqueue()
        self.backend.fail_reading = RedisDown("Error 111 connecting to redis:6379. Connection refused.")
        response = self.get(task_id)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "the task queue is not available", "code": "task_queue_unavailable"})


class ConfigTests(unittest.TestCase):
    BASE = {"JWT_SECRET_KEY": "x" * 40, "ACCESS_TOKEN_EXPIRE_MINUTES": "30", "DATABASE_URL": "postgresql://u:p@db:5432/x"}

    def test_redis_url_is_optional(self) -> None:
        settings = Settings.from_env(self.BASE)
        self.assertEqual(settings.redis_url, "")
        self.assertIsNone(build_task_queue(settings))

    def test_redis_url_is_read_and_hidden(self) -> None:
        settings = Settings.from_env({**self.BASE, "REDIS_URL": " redis://:redis-Secret-1@redis:6379/0 "})
        self.assertEqual(settings.redis_url, "redis://:redis-Secret-1@redis:6379/0")
        self.assertNotIn("redis-Secret-1", repr(settings))
        self.assertEqual(type(build_task_queue(settings)).__name__, "TaskQueueClient")

    def test_invalid_redis_url_does_not_start_and_hides_the_value(self) -> None:
        for url in ("http://:redis-Secret-1@redis:6379/0", "redis://:redis-Secret-1@redis/0"):
            with self.subTest(url=url.split("@")[1]):
                with self.assertRaises(ConfigError) as raised:
                    build_task_queue(Settings.from_env({**self.BASE, "REDIS_URL": url}))
                self.assertIn("REDIS_URL", str(raised.exception))
                self.assertNotIn("redis-Secret-1", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
