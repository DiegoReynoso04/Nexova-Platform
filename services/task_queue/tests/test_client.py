"""`TaskQueueClient` (productor) y los metadatos de A10, sin Redis: `MemoryStore` + `EagerBackend`."""

import json
import unittest

from kombu.exceptions import OperationalError as BrokerDown
from redis.exceptions import ConnectionError as RedisDown

from task_queue import metadata
from task_queue.client import STATUS_BY_CELERY_STATE, TaskQueueClient, TaskQueueUnavailableError, public_status
from task_queue.config import DEDUPE_TTL_SECONDS, METADATA_SAFETY_TTL_SECONDS, RESULT_EXPIRES_SECONDS
from task_queue.memory import EagerBackend, MemoryStore
from task_queue.metadata import dedupe_key, finish_metadata, metadata_key

NAME = "task_queue.example"
OWNER, OTHER = "owner-1", "other-2"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ClientCase(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = MemoryStore(self.clock)
        self.backend = EagerBackend({NAME: lambda **kwargs: {"echo": kwargs}}, hold=True)
        self.ids = iter(f"00000000-0000-4000-8000-00000000000{n}" for n in range(1, 10))
        self.client = TaskQueueClient(store=self.store, backend=self.backend, new_id=lambda: next(self.ids))

    def submit(self, owner=OWNER, scope="a|b", **kwargs):
        return self.client.submit(NAME, kwargs or {"start": "s", "end": "e"}, owner_id=owner, dedupe_scope=scope)


class SubmitTests(ClientCase):
    def test_metadata_is_saved_before_publishing_with_the_safety_ttl(self):
        seen = []
        original = self.backend.send
        self.backend.send = lambda name, kwargs, task_id: (seen.append(self.store.get(metadata_key(task_id))), original(name, kwargs, task_id))
        submission = self.submit()
        self.assertIsNotNone(seen[0])
        self.assertEqual(json.loads(seen[0])["owner_id"], OWNER)
        self.assertEqual(self.store.ttl(metadata_key(submission.task_id)), METADATA_SAFETY_TTL_SECONDS)

    def test_the_message_carries_exactly_the_given_references(self):
        self.submit(start="2026-11-13T00:00:00.000Z", end="2026-11-20T00:00:00.000Z")
        [(name, kwargs, _)] = self.backend.sent
        self.assertEqual((name, kwargs), (NAME, {"start": "2026-11-13T00:00:00.000Z", "end": "2026-11-20T00:00:00.000Z"}))

    def test_same_owner_and_scope_within_the_ttl_reuse_the_task(self):
        first, second = self.submit(), self.submit()
        self.assertEqual(first.task_id, second.task_id)
        self.assertEqual((first.deduplicated, second.deduplicated), (False, True))
        self.assertEqual(len(self.backend.sent), 1)
        self.assertEqual(self.store.ttl(dedupe_key(NAME, OWNER, "a|b")), DEDUPE_TTL_SECONDS)

    def test_another_owner_or_scope_is_another_task(self):
        ids = {self.submit().task_id, self.submit(owner=OTHER).task_id, self.submit(scope="a|c").task_id}
        self.assertEqual(len(ids), 3)

    def test_after_the_ttl_a_new_task(self):
        first = self.submit()
        self.clock.now += DEDUPE_TTL_SECONDS
        self.assertNotEqual(self.submit().task_id, first.task_id)

    def test_a_failed_or_revoked_task_is_replaced(self):
        for state in ("FAILURE", "REVOKED"):
            with self.subTest(state=state):
                self.store.values.clear()
                failed = self.submit()
                self.backend.set_state(failed.task_id, state)
                replacement = self.submit()
                self.assertNotEqual(replacement.task_id, failed.task_id)
                self.assertEqual(self.store.get(dedupe_key(NAME, OWNER, "a|b")), replacement.task_id)

    def test_running_and_finished_tasks_are_reused(self):
        for state in ("PENDING", "STARTED", "RETRY", "SUCCESS"):
            with self.subTest(state=state):
                self.store.values.clear()
                first = self.submit()
                self.backend.set_state(first.task_id, state)
                self.assertEqual(self.submit().task_id, first.task_id)

    def test_without_scope_there_is_no_dedupe(self):
        self.assertNotEqual(self.submit(scope=None).task_id, self.submit(scope=None).task_id)

    def test_a_broker_failure_raises_unavailable_and_cleans_up(self):
        self.backend.fail_sending = BrokerDown("Error 111 connecting to redis://:pw@redis:6379/0")
        with self.assertRaises(TaskQueueUnavailableError) as raised:
            self.submit()
        self.assertEqual(str(raised.exception), "OperationalError")
        self.assertIsNone(raised.exception.__cause__)
        self.assertEqual(self.store.values, {})

    def test_a_redis_failure_raises_unavailable(self):
        class DownStore(MemoryStore):
            def set(self, *args, **kwargs):
                raise RedisDown("refused")

        client = TaskQueueClient(store=DownStore(), backend=self.backend)
        with self.assertRaises(TaskQueueUnavailableError):
            client.submit(NAME, {}, owner_id=OWNER, dedupe_scope="x")
        self.assertEqual(self.backend.sent, [])


class StatusTests(ClientCase):
    def test_unknown_expired_or_foreign_ids_are_none(self):
        task_id = self.submit().task_id
        self.assertIsNone(self.client.status("00000000-0000-4000-8000-0000000000ff", viewer_id=OWNER, viewer_is_admin=False))
        self.assertIsNone(self.client.status(task_id, viewer_id=OTHER, viewer_is_admin=False))
        self.assertIsNotNone(self.client.status(task_id, viewer_id=OTHER, viewer_is_admin=True))
        self.clock.now += METADATA_SAFETY_TTL_SECONDS
        self.assertIsNone(self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False))

    def test_states_and_results(self):
        task_id = self.submit().task_id
        self.assertEqual(self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False).status, "pending")
        self.backend.run(task_id)
        status = self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False)
        self.assertEqual((status.status, status.task_name, status.result), ("success", NAME, {"echo": {"start": "s", "end": "e"}}))
        self.backend.set_state(task_id, "FAILURE", RuntimeError("x"))
        self.assertIsNone(self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False).result)

    def test_redis_down_while_reading_is_unavailable(self):
        task_id = self.submit().task_id
        self.backend.fail_reading = RedisDown("refused")
        with self.assertRaises(TaskQueueUnavailableError):
            self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False)

    def test_mapping_of_the_six_celery_states(self):
        self.assertEqual(
            {state: public_status(state) for state in ("PENDING", "STARTED", "RETRY", "SUCCESS", "FAILURE", "REVOKED")},
            {"PENDING": "pending", "STARTED": "started", "RETRY": "started", "SUCCESS": "success", "FAILURE": "failure", "REVOKED": "failure"},
        )
        self.assertEqual(set(STATUS_BY_CELERY_STATE.values()), {"pending", "started", "success", "failure"})
        self.assertEqual(public_status("SOMETHING_NEW"), "pending")


class MetadataLifetimeTests(ClientCase):
    """A10: viva mientras está en cola o en curso; al terminar, caduca con el resultado."""

    def test_a_queued_task_survives_hours_without_a_worker(self):
        task_id = self.submit().task_id
        self.clock.now += 6 * 3600  # el worker lleva 6 h parado
        self.assertEqual(self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False).status, "pending")

    def test_finishing_aligns_the_ttl_with_the_result(self):
        task_id = self.submit().task_id
        finish_metadata(task_id, store=self.store)
        self.assertEqual(self.store.ttl(metadata_key(task_id)), RESULT_EXPIRES_SECONDS)
        self.clock.now += RESULT_EXPIRES_SECONDS
        self.assertIsNone(self.client.status(task_id, viewer_id=OWNER, viewer_is_admin=False))

    def test_finishing_never_raises(self):
        class DownStore(MemoryStore):
            def expire(self, *args):
                raise RedisDown("refused")

        with self.assertLogs("task_queue", "WARNING") as logs:
            finish_metadata("t-1", store=DownStore())
        self.assertIn("status=metadata_not_finished cause=ConnectionError", logs.output[0])

    def test_finishing_an_unknown_key_is_a_no_op(self):
        finish_metadata("never-enqueued", store=self.store)
        self.assertEqual(self.store.values, {})

    def test_keys(self):
        self.assertEqual(metadata_key("abc"), "nexova:task:abc")
        self.assertEqual(dedupe_key("n", "u", "s"), "nexova:dedupe:n:u:s")
        self.assertEqual(metadata.METADATA_PREFIX, "nexova:task:")


class FromRedisUrlTests(unittest.TestCase):
    def test_builds_without_connecting(self):
        """El calentamiento (transporte, backend, productor, clase del resultado) no abre ninguna conexión."""
        import socket
        from unittest import mock

        def no_network(*args, **kwargs):
            raise AssertionError("from_redis_url must not open a connection")

        with mock.patch.object(socket.socket, "connect", no_network), mock.patch.object(socket, "create_connection", no_network):
            client = TaskQueueClient.from_redis_url("redis://:pw@127.0.0.1:6399/0")
        self.assertEqual(client.backend.celery.conf.broker_url, "redis://:pw@127.0.0.1:6399/0")
        self.assertEqual(client.store.client.connection_pool.connection_kwargs["db"], 1)
        # La API no incluye ningún módulo de tareas: envía por nombre (el worker las registra).
        self.assertEqual(list(client.backend.celery.conf.include), [])


if __name__ == "__main__":
    unittest.main()
