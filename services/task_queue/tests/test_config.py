"""`REDIS_URL` y los ajustes de Celery de A7 (docs/async-tasks/analysis.md)."""

import unittest

from task_queue import config
from task_queue.config import ConfigError, TaskQueueSettings, celery_config

SECRET = "s3cr3t-redis-password"


class RedisUrlTests(unittest.TestCase):
    def test_broker_uses_the_url_database_and_the_backend_the_next_one(self):
        settings = TaskQueueSettings.from_redis_url(f"redis://:{SECRET}@redis:6379/0")
        self.assertEqual(settings.broker_url, f"redis://:{SECRET}@redis:6379/0")
        self.assertEqual(settings.result_backend, f"redis://:{SECRET}@redis:6379/1")

    def test_without_database_the_broker_uses_zero(self):
        settings = TaskQueueSettings.from_redis_url("redis://redis:6379")
        self.assertEqual((settings.broker_url, settings.result_backend), ("redis://redis:6379/0", "redis://redis:6379/1"))

    def test_another_database_moves_both(self):
        settings = TaskQueueSettings.from_redis_url("rediss://:pw@cache.example.invalid:6380/3/")
        self.assertEqual(settings.broker_url, "rediss://:pw@cache.example.invalid:6380/3")
        self.assertEqual(settings.result_backend, "rediss://:pw@cache.example.invalid:6380/4")

    def test_from_env_reads_only_redis_url(self):
        settings = TaskQueueSettings.from_env({"REDIS_URL": " redis://redis:6379/0 ", "DATABASE_URL": "postgresql://x"})
        self.assertEqual(settings.broker_url, "redis://redis:6379/0")

    def test_invalid_values_raise_without_repeating_the_url(self):
        cases = {
            "missing": "",
            "scheme": f"http://:{SECRET}@redis:6379/0",
            "no port": f"redis://:{SECRET}@redis/0",
            "bad port": f"redis://:{SECRET}@redis:port/0",
            "no host": f"redis://:{SECRET}@:6379/0",
            "db not a number": f"redis://:{SECRET}@redis:6379/abc",
            "db too high": f"redis://:{SECRET}@redis:6379/15",
            "query": f"redis://:{SECRET}@redis:6379/0?ssl=true",
        }
        for name, url in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ConfigError) as raised:
                    TaskQueueSettings.from_redis_url(url)
                message = str(raised.exception)
                self.assertIn("REDIS_URL", message)
                self.assertNotIn(SECRET, message)
                self.assertIsNone(raised.exception.__cause__)

    def test_missing_variable(self):
        with self.assertRaisesRegex(ConfigError, "REDIS_URL is required"):
            TaskQueueSettings.from_env({})

    def test_repr_hides_the_urls(self):
        settings = TaskQueueSettings.from_redis_url(f"redis://:{SECRET}@redis:6379/0")
        self.assertNotIn(SECRET, repr(settings))
        self.assertNotIn("redis:6379", repr(settings))


class CeleryConfigTests(unittest.TestCase):
    """Cada valor de A7, decidido por el usuario el 2026-11-20."""

    def setUp(self):
        self.conf = celery_config(TaskQueueSettings.from_redis_url("redis://:pw@redis:6379/0"))

    def test_broker_and_backend(self):
        self.assertEqual(self.conf["broker_url"], "redis://:pw@redis:6379/0")
        self.assertEqual(self.conf["result_backend"], "redis://:pw@redis:6379/1")

    def test_json_only(self):
        self.assertEqual(self.conf["task_serializer"], "json")
        self.assertEqual(self.conf["result_serializer"], "json")
        self.assertEqual(self.conf["accept_content"], ["json"])
        self.assertEqual(self.conf["result_accept_content"], ["json"])

    def test_ack_after_success_and_redelivery(self):
        self.assertIs(self.conf["task_acks_late"], True)
        self.assertIs(self.conf["task_reject_on_worker_lost"], True)
        self.assertIs(self.conf["worker_cancel_long_running_tasks_on_connection_loss"], True)
        self.assertEqual(self.conf["broker_transport_options"]["visibility_timeout"], 600)

    def test_every_task_has_a_timeout(self):
        self.assertEqual((self.conf["task_soft_time_limit"], self.conf["task_time_limit"]), (120, 150))
        self.assertLess(self.conf["task_soft_time_limit"], self.conf["task_time_limit"])
        # La visibilidad cubre la ejecución más larga con margen para la cuenta atrás de un reintento.
        self.assertGreater(self.conf["broker_transport_options"]["visibility_timeout"], self.conf["task_time_limit"] + 60)

    def test_fair_dispatch_and_worker_limits(self):
        self.assertEqual(self.conf["worker_prefetch_multiplier"], 1)
        self.assertEqual(self.conf["worker_concurrency"], config.WORKER_CONCURRENCY)
        self.assertEqual(self.conf["worker_max_tasks_per_child"], config.WORKER_MAX_TASKS_PER_CHILD)

    def test_results_expire_and_started_is_tracked(self):
        self.assertEqual(self.conf["result_expires"], 3600)
        self.assertIs(self.conf["task_track_started"], True)

    def test_events_for_flower(self):
        self.assertIs(self.conf["worker_send_task_events"], True)
        self.assertIs(self.conf["task_send_sent_event"], True)

    def test_publishing_fails_fast(self):
        policy = self.conf["task_publish_retry_policy"]
        self.assertEqual(policy["max_retries"], 1)
        self.assertLessEqual(policy["interval_max"], 0.2)
        self.assertEqual(self.conf["broker_connection_timeout"], 2)
        self.assertEqual(self.conf["broker_transport_options"]["socket_connect_timeout"], 2)
        self.assertEqual(self.conf["redis_socket_connect_timeout"], 2)

    def test_queue_and_clock(self):
        self.assertEqual(self.conf["task_default_queue"], "nexova.tasks")
        self.assertEqual((self.conf["timezone"], self.conf["enable_utc"]), ("UTC", True))


if __name__ == "__main__":
    unittest.main()
