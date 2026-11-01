"""Caché del resumen y del listado del gestor de incidencias (ticket de caching, D1–D4).

Las lecturas del repositorio se cuentan envolviendo `_documents`, el único punto
por el que el listado y el resumen leen la TinyDB.
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from nexova_shared.incidents import prepare_seed_batch

from app.core.cache import ResponseCache
from app.core.config import Settings
from app.modules.incident_manager.router import CACHE_NAMESPACE, CACHE_TTL_SECONDS

from .test_cache import FakeClock
from .test_incident_manager_api import ACCEPTANCE_FIXTURE, SUMMARY_URL, URL, managed_client, valid_incident


class IncidentCacheTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.client = managed_client(self, Settings(incidents_db_path=Path(directory.name) / "incidents.json"))
        self.app: Any = self.client.app
        self.clock = FakeClock()
        self.app.state.response_cache = ResponseCache(clock=self.clock)
        self.repository = self.app.state.incident_repository
        self.reads = 0
        documents = self.repository._documents

        def counted() -> Any:
            self.reads += 1
            return documents()

        self.repository._documents = counted
        self.incident = self.create()

    def create(self, **changes: Any) -> dict[str, Any]:
        response = self.client.post(URL, json=valid_incident(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def reads_for(self, url: str, **params: str) -> int:
        before = self.reads
        response = self.client.get(url, params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return self.reads - before

    def total(self) -> int:
        return self.client.get(SUMMARY_URL).json()["total"]

    def warm(self) -> None:
        self.assertEqual(self.reads_for(SUMMARY_URL), 1)
        self.assertEqual(self.reads_for(URL), 1)
        self.assertEqual(self.reads_for(URL, status="open"), 1)


class HitTests(IncidentCacheTestCase):
    def test_ttl_is_30_seconds_in_the_incidents_namespace(self) -> None:
        self.assertEqual((CACHE_NAMESPACE, CACHE_TTL_SECONDS), ("incidents", 30))

    def test_a_hit_on_the_summary_does_not_read_the_database(self) -> None:
        self.assertEqual(self.reads_for(SUMMARY_URL), 1)
        self.assertEqual(self.reads_for(SUMMARY_URL), 0)

    def test_a_hit_on_the_list_with_the_same_filters_does_not_read_the_database(self) -> None:
        self.assertEqual(self.reads_for(URL, status="open", branch="central"), 1)
        self.assertEqual(self.reads_for(URL, status="open", branch="central"), 0)

    def test_parameter_order_shares_the_entry(self) -> None:
        self.assertEqual(self.reads_for(f"{URL}?status=open&branch=central"), 1)
        self.assertEqual(self.reads_for(f"{URL}?branch=central&status=open"), 0)

    def test_two_filter_combinations_do_not_overwrite_each_other(self) -> None:
        self.create(branch="miami_office", category="sla_breach")
        central = self.client.get(URL, params={"branch": "central"}).json()
        miami = self.client.get(URL, params={"branch": "miami_office"}).json()
        everything = self.client.get(URL).json()
        self.assertEqual([item["branch"] for item in central], ["central"])
        self.assertEqual([item["branch"] for item in miami], ["miami_office"])
        self.assertEqual(len(everything), 2)
        # Ya en caché: cada combinación sigue devolviendo lo suyo.
        self.assertEqual(self.client.get(URL, params={"branch": "central"}).json(), central)
        self.assertEqual(self.client.get(URL, params={"branch": "miami_office"}).json(), miami)
        self.assertEqual(self.app.state.response_cache.size(CACHE_NAMESPACE), 3)

    def test_an_invalid_filter_is_400_and_is_not_cached(self) -> None:
        for params in ({"status": "closed"}, {"branch": ""}, {"category": "OTHER"}):
            with self.subTest(params=params):
                response = self.client.get(URL, params=params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], "validation_error")
        self.assertEqual(self.app.state.response_cache.size(CACHE_NAMESPACE), 0)
        self.assertEqual(self.reads, 0)

    def test_the_value_expires_after_30_seconds(self) -> None:
        self.assertEqual(self.reads_for(SUMMARY_URL), 1)
        self.clock.now += CACHE_TTL_SECONDS - 0.001
        self.assertEqual(self.reads_for(SUMMARY_URL), 0)
        self.clock.now += 0.001
        self.assertEqual(self.reads_for(SUMMARY_URL), 1)


class InvalidationTests(IncidentCacheTestCase):
    def assert_cold(self) -> None:
        self.assertEqual(self.reads_for(SUMMARY_URL), 1)
        self.assertEqual(self.reads_for(URL), 1)
        self.assertEqual(self.reads_for(URL, status="open"), 1)

    def test_creating_an_incident_invalidates_summary_and_every_list(self) -> None:
        self.warm()
        self.create(title="Second synthetic incident")
        self.assert_cold()
        self.assertEqual(self.total(), 2)

    def test_a_valid_status_change_invalidates(self) -> None:
        self.warm()
        response = self.client.patch(f"{URL}/{self.incident['id']}/status", json={"status": "in_progress"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assert_cold()
        self.assertEqual(self.client.get(URL, params={"status": "open"}).json(), [])
        self.assertEqual(self.client.get(SUMMARY_URL).json()["by_status"]["in_progress"], 1)

    def test_failed_writes_do_not_invalidate(self) -> None:
        self.warm()
        failures = [
            # 400: transición no permitida (open → resolved).
            ("PATCH", f"{URL}/{self.incident['id']}/status", {"status": "resolved"}, 400),
            # 400: cuerpo no válido.
            ("PATCH", f"{URL}/{self.incident['id']}/status", {"status": "closed"}, 400),
            # 404: la incidencia no existe.
            ("PATCH", f"{URL}/00000000-0000-4000-8000-000000000000/status", {"status": "in_progress"}, 404),
            # 400: alta no válida.
            ("POST", URL, valid_incident(branch="madrid"), 400),
        ]
        for method, url, body, status in failures:
            with self.subTest(method=method, url=url, status=status):
                self.assertEqual(self.client.request(method, url, json=body).status_code, status)
                self.assertEqual(self.reads_for(SUMMARY_URL), 0)
                self.assertEqual(self.reads_for(URL), 0)
                self.assertEqual(self.reads_for(URL, status="open"), 0)

    def test_the_seed_does_not_invalidate_and_shows_up_after_the_ttl(self) -> None:
        self.assertEqual(self.total(), 1)
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            self.repository.seed(prepare_seed_batch(stream).incidents)
        # El seed escribe en TinyDB sin pasar por la API: la caché no se entera.
        self.assertEqual(self.total(), 1)
        self.clock.now += CACHE_TTL_SECONDS
        self.assertEqual(self.total(), 97)


class AuthenticationTests(IncidentCacheTestCase):
    def test_without_a_token_the_cached_routes_are_still_401(self) -> None:
        urls = [SUMMARY_URL, URL, f"{URL}?status=open"]
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.client.headers.pop("Authorization")
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 401)


if __name__ == "__main__":
    unittest.main()
