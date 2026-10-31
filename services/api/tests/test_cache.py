"""Caché en memoria con TTL (app/core/cache.py; docs/caching-analysis.md, D2–D4).

El reloj es inyectable: el TTL se prueba avanzando un reloj falso, sin `sleep`.
"""

import threading
import unittest

from app.core.cache import DEFAULT_MAX_ENTRIES, ResponseCache

from .support import make_client


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Counter:
    """`compute` que cuenta sus llamadas y devuelve un valor nuevo en cada una."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return f"value-{self.calls}"


class TtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.cache = ResponseCache(clock=self.clock)
        self.compute = Counter()

    def test_a_hit_returns_the_stored_value_without_computing(self) -> None:
        first = self.cache.get_or_set("ns", "k", 60, self.compute)
        second = self.cache.get_or_set("ns", "k", 60, self.compute)
        self.assertEqual((first, second), ("value-1", "value-1"))
        self.assertEqual(self.compute.calls, 1)

    def test_the_value_expires_exactly_at_the_ttl(self) -> None:
        self.cache.get_or_set("ns", "k", 60, self.compute)
        self.clock.now += 59.999
        self.assertEqual(self.cache.get_or_set("ns", "k", 60, self.compute), "value-1")
        self.clock.now += 0.001
        self.assertEqual(self.cache.get_or_set("ns", "k", 60, self.compute), "value-2")
        self.assertEqual(self.compute.calls, 2)

    def test_each_key_has_its_own_value(self) -> None:
        self.assertEqual(self.cache.get_or_set("ns", ("open", None), 60, self.compute), "value-1")
        self.assertEqual(self.cache.get_or_set("ns", ("resolved", None), 60, self.compute), "value-2")
        self.assertEqual(self.cache.get_or_set("ns", ("open", None), 60, self.compute), "value-1")

    def test_ttl_must_be_positive(self) -> None:
        for ttl in (0, -1):
            with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                self.cache.get_or_set("ns", "k", ttl, self.compute)

    def test_a_failing_compute_stores_nothing(self) -> None:
        def boom() -> str:
            raise RuntimeError("database down")

        with self.assertRaises(RuntimeError):
            self.cache.get_or_set("ns", "k", 60, boom)
        self.assertEqual(self.cache.size("ns"), 0)
        self.assertEqual(self.cache.get_or_set("ns", "k", 60, self.compute), "value-1")


class InvalidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cache = ResponseCache(clock=FakeClock())
        self.compute = Counter()

    def test_invalidate_clears_every_key_of_the_namespace(self) -> None:
        self.cache.get_or_set("inventory", "products", 60, self.compute)
        self.cache.get_or_set("inventory", ("product", 1), 60, self.compute)
        self.cache.invalidate("inventory")
        self.assertEqual(self.cache.size("inventory"), 0)
        self.assertEqual(self.cache.get_or_set("inventory", "products", 60, self.compute), "value-3")

    def test_invalidate_leaves_other_namespaces_alone(self) -> None:
        self.cache.get_or_set("inventory", "products", 60, self.compute)
        self.cache.get_or_set("incidents", "summary", 60, self.compute)
        self.cache.invalidate("inventory")
        self.assertEqual(self.cache.get_or_set("incidents", "summary", 60, self.compute), "value-2")
        self.assertEqual(self.compute.calls, 2)

    def test_a_computation_that_started_before_an_invalidation_is_not_stored(self) -> None:
        def stale_read() -> str:
            # Una escritura confirma e invalida mientras esta lectura está en curso.
            self.cache.invalidate("inventory")
            return "stale"

        self.assertEqual(self.cache.get_or_set("inventory", "products", 60, stale_read), "stale")
        self.assertEqual(self.cache.size("inventory"), 0)
        self.assertEqual(self.cache.get_or_set("inventory", "products", 60, self.compute), "value-1")


class MaxEntriesTests(unittest.TestCase):
    def test_default_is_64_per_namespace(self) -> None:
        self.assertEqual(DEFAULT_MAX_ENTRIES, 64)

    def test_the_oldest_entry_is_evicted_past_the_limit(self) -> None:
        cache = ResponseCache(clock=FakeClock(), max_entries=3)
        compute = Counter()
        for key in ("a", "b", "c", "d"):
            cache.get_or_set("ns", key, 60, compute)
        self.assertEqual(cache.size("ns"), 3)
        # "a" salió; "b", "c" y "d" siguen.
        self.assertEqual(cache.get_or_set("ns", "a", 60, compute), "value-5")
        self.assertEqual(cache.get_or_set("ns", "d", 60, compute), "value-4")

    def test_the_limit_applies_per_namespace(self) -> None:
        cache = ResponseCache(clock=FakeClock(), max_entries=2)
        compute = Counter()
        for key in ("a", "b"):
            cache.get_or_set("one", key, 60, compute)
            cache.get_or_set("two", key, 60, compute)
        self.assertEqual((cache.size("one"), cache.size("two")), (2, 2))

    def test_max_entries_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            ResponseCache(max_entries=0)


class ConcurrencyTests(unittest.TestCase):
    def test_parallel_readers_and_invalidations_do_not_corrupt_the_cache(self) -> None:
        cache = ResponseCache(max_entries=8)
        errors: list[BaseException] = []
        barrier = threading.Barrier(8)

        def worker(index: int) -> None:
            try:
                barrier.wait()
                for round_ in range(500):
                    key = (index + round_) % 16
                    value = cache.get_or_set("ns", key, 60, lambda key=key: key * 2)
                    assert value == key * 2, value
                    if round_ % 50 == 0:
                        cache.invalidate("ns")
            except BaseException as error:  # noqa: BLE001 — se comprueba en el hilo principal
                errors.append(error)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertLessEqual(cache.size("ns"), 8)


class AppWiringTests(unittest.TestCase):
    def test_each_app_gets_its_own_empty_cache(self) -> None:
        first, second = make_client(), make_client()
        first_cache = first.app.state.response_cache  # type: ignore[attr-defined]
        second_cache = second.app.state.response_cache  # type: ignore[attr-defined]
        self.assertIsInstance(first_cache, ResponseCache)
        self.assertIsNot(first_cache, second_cache)


if __name__ == "__main__":
    unittest.main()
