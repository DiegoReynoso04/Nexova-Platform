"""Backoff propio (A8-B): nunca por debajo de base·2^n. S3: el jitter de Celery sí puede dar 0."""

import unittest
from unittest import mock

from celery.utils.time import get_exponential_backoff_interval

from task_queue.retries import backoff_countdown, backoff_floor


class BackoffTests(unittest.TestCase):
    def test_floors_are_base_times_two_to_the_n(self):
        self.assertEqual([backoff_floor(n) for n in range(3)], [2, 4, 8])

    def test_jitter_only_adds_up_to_one_base(self):
        for retries, (low, high) in enumerate([(2, 4), (4, 6), (8, 10)]):
            with self.subTest(retries=retries):
                self.assertEqual(backoff_countdown(retries, rng=lambda: 0.0), low)
                self.assertLess(backoff_countdown(retries, rng=lambda: 0.999999), high)

    def test_never_below_the_floor_with_the_real_random(self):
        for retries in range(3):
            for _ in range(2000):
                self.assertGreaterEqual(backoff_countdown(retries), backoff_floor(retries))

    def test_cap(self):
        self.assertEqual(backoff_floor(10), 60)
        self.assertEqual(backoff_countdown(10, rng=lambda: 0.5), 61)

    def test_negative_retries_rejected(self):
        with self.assertRaises(ValueError):
            backoff_floor(-1)

    def test_celery_full_jitter_can_be_immediate(self):
        """S3, verificado con la versión instalada: `random.randrange(countdown + 1)` puede dar 0."""
        with mock.patch("celery.utils.time.random.randrange", return_value=0):
            self.assertEqual(get_exponential_backoff_interval(2, 0, 60, full_jitter=True), 0)
        self.assertEqual(get_exponential_backoff_interval(2, 2, 60, full_jitter=False), 8)


if __name__ == "__main__":
    unittest.main()
