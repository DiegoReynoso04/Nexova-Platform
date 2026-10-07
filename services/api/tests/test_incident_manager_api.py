"""API HTTP del gestor centralizado de incidencias (F4, SPECS.md Parte E).

Cada test usa su propia base TinyDB temporal: nunca toca services/api/data/.
Datos ficticios (`example.invalid`).
"""

import itertools
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from httpx import Response
from nexova_shared.incidents import Branch, IncidentCategory, IncidentOrigin, IncidentStatus, prepare_seed_batch

from app.core.config import Settings
from app.core.errors import INTERNAL_ERROR_DETAIL
from app.modules.incident_manager.repository import IncidentRepository
from app.modules.incident_manager.router import get_incident_repository

from .suppliers_support import FakeClock
from .support import ANALYZE_URL, EXPORT_URL, REPO_ROOT, capture_logs, make_client

URL = "/api/incidents"
SUMMARY_URL = f"{URL}/summary"
ACCEPTANCE_FIXTURE = (
    REPO_ROOT / "packages" / "incident-analyzer" / "tests" / "fixtures" / "incidents-acceptance-synthetic.csv"
)
LEAK = "leak@example.invalid"

OPEN, IN_PROGRESS, RESOLVED, DISCARDED = "open", "in_progress", "resolved", "discarded"
# Las 16 combinaciones (origen, destino), escritas a mano desde el CONTEXT.
TRANSITIONS = {
    (OPEN, OPEN): False,
    (OPEN, IN_PROGRESS): True,
    (OPEN, RESOLVED): False,
    (OPEN, DISCARDED): True,
    (IN_PROGRESS, OPEN): False,
    (IN_PROGRESS, IN_PROGRESS): False,
    (IN_PROGRESS, RESOLVED): True,
    (IN_PROGRESS, DISCARDED): True,
    (RESOLVED, OPEN): False,
    (RESOLVED, IN_PROGRESS): False,
    (RESOLVED, RESOLVED): False,
    (RESOLVED, DISCARDED): False,
    (DISCARDED, OPEN): False,
    (DISCARDED, IN_PROGRESS): False,
    (DISCARDED, RESOLVED): False,
    (DISCARDED, DISCARDED): False,
}
# Camino válido desde `open` hasta cada estado.
PATH_TO = {OPEN: [], IN_PROGRESS: [IN_PROGRESS], RESOLVED: [IN_PROGRESS, RESOLVED], DISCARDED: [DISCARDED]}


def valid_incident(**changes: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "title": "Synthetic incident",
        "description": "Synthetic description of the incident",
        "category": "technical_failure",
        "origin": "internal",
        "branch": "central",
    }
    body.update(changes)
    return body


def without(field: str) -> dict[str, Any]:
    body = valid_incident()
    del body[field]
    return body


def managed_client(test: unittest.TestCase, settings: Settings | None = None, *, authenticated: bool = True) -> TestClient:
    """`make_client` + limpieza explícita de su base de usuarios temporal."""
    client = make_client(settings, authenticated=authenticated)
    test.addCleanup(client.auth_dir.cleanup)  # type: ignore[attr-defined]
    return client


class IncidentApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "incidents.json"
        self.client = managed_client(self, Settings(incidents_db_path=self.db_path))

    @property
    def repository(self) -> IncidentRepository:
        repository = self.client.app.state.incident_repository  # type: ignore[attr-defined]
        assert isinstance(repository, IncidentRepository)
        return repository

    def create(self, **changes: Any) -> dict[str, Any]:
        response = self.client.post(URL, json=valid_incident(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def patch_status(self, incident_id: str, status: Any) -> Response:
        return self.client.patch(f"{URL}/{incident_id}/status", json={"status": status})

    def assertFieldErrors(self, response: Response, expected: list[tuple[str, str]], code: str = "validation_error") -> None:
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertEqual(set(body), {"code", "detail"})
        self.assertEqual(body["code"], code)
        self.assertEqual([(error["field"], error["error"]) for error in body["detail"]], expected)
        for error in body["detail"]:
            self.assertEqual(set(error), {"field", "error", "message"})
            self.assertTrue(error["message"])

    def seed_fixture(self) -> None:
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            self.repository.seed(prepare_seed_batch(stream).incidents)


class CreateTests(IncidentApiTestCase):
    def test_created_incident(self) -> None:
        response = self.client.post(URL, json=valid_incident(origin="branch", branch="miami_office", category="sla_breach"))
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            set(body), {"id", "title", "description", "category", "status", "origin", "branch", "created_at", "updated_at"}
        )
        self.assertEqual(UUID(body["id"]).version, 4)
        self.assertEqual(body["status"], "open")
        self.assertEqual((body["origin"], body["branch"], body["category"]), ("branch", "miami_office", "sla_breach"))
        self.assertEqual(body["created_at"], body["updated_at"])
        self.assertTrue(body["created_at"].endswith("Z"))
        self.assertEqual(self.client.get(f"{URL}/{body['id']}").json(), body)

    def test_explicit_open_status_and_trimmed_text(self) -> None:
        body = self.create(status="open", title="  Synthetic  ", description="\tText\n")
        self.assertEqual((body["status"], body["title"], body["description"]), ("open", "Synthetic", "Text"))

    def test_every_vocabulary_value_is_accepted(self) -> None:
        for branch, origin in itertools.product(Branch, IncidentOrigin):
            self.create(branch=branch.value, origin=origin.value)
        for category in IncidentCategory:
            self.create(category=category.value)

    def test_title_limit_and_description_without_maximum(self) -> None:
        self.assertEqual(len(self.create(title="x" * 120)["title"]), 120)
        self.assertEqual(len(self.create(description="y" * 50_000)["description"]), 50_000)

    def test_each_required_field_missing(self) -> None:
        for field in ("title", "description", "category", "origin", "branch"):
            with self.subTest(field=field):
                self.assertFieldErrors(self.client.post(URL, json=without(field)), [(field, "missing")])

    def test_null_counts_as_missing(self) -> None:
        self.assertFieldErrors(self.client.post(URL, json=valid_incident(branch=None)), [("branch", "missing")])

    def test_branch_is_required_for_every_origin(self) -> None:
        for origin in IncidentOrigin:
            with self.subTest(origin=origin.value):
                body = valid_incident(origin=origin.value)
                del body["branch"]
                self.assertFieldErrors(self.client.post(URL, json=body), [("branch", "missing")])

    def test_blank_text(self) -> None:
        for field in ("title", "description"):
            with self.subTest(field=field):
                self.assertFieldErrors(self.client.post(URL, json=valid_incident(**{field: "  "})), [(field, "blank")])

    def test_values_outside_the_context(self) -> None:
        cases = {
            "category": ["TECHNICAL", "Technical_Failure", "headquarters", 3],
            "origin": ["client", "Customer"],
            "branch": ["headquarters", "Central", "miami"],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.client.post(URL, json=valid_incident(**{field: value}))
                    self.assertFieldErrors(response, [(field, "invalid_choice")])

    def test_title_longer_than_120(self) -> None:
        response = self.client.post(URL, json=valid_incident(title="x" * 121))
        self.assertFieldErrors(response, [("title", "too_long")])
        self.assertEqual(response.json()["detail"][0]["message"], "title must be at most 120 characters")

    def test_text_of_another_type(self) -> None:
        self.assertFieldErrors(self.client.post(URL, json=valid_incident(title=12)), [("title", "invalid_type")])

    def test_unknown_field(self) -> None:
        self.assertFieldErrors(self.client.post(URL, json=valid_incident(priority="high")), [("priority", "unknown_field")])

    def test_system_fields_sent_by_the_client(self) -> None:
        for field, value in (("id", str(uuid4())), ("created_at", "2026-01-01T00:00:00Z"), ("updated_at", "2026-01-01")):
            with self.subTest(field=field):
                self.assertFieldErrors(self.client.post(URL, json=valid_incident(**{field: value})), [(field, "unknown_field")])

    def test_status_other_than_open(self) -> None:
        for status in (IN_PROGRESS, RESOLVED, DISCARDED, "closed"):
            with self.subTest(status=status):
                response = self.client.post(URL, json=valid_incident(status=status))
                self.assertFieldErrors(response, [("status", "invalid_choice")])
                self.assertEqual(response.json()["detail"][0]["message"], "status must be one of: open")

    def test_body_that_is_not_a_json_object(self) -> None:
        cases: list[dict[str, Any]] = [
            {"content": b"not json", "headers": {"Content-Type": "application/json"}},
            {"content": b'{"title": ', "headers": {"Content-Type": "application/json"}},
            {"content": b"[1, 2]", "headers": {"Content-Type": "application/json"}},
            {"content": b'"text"', "headers": {"Content-Type": "application/json"}},
            {"content": b"null", "headers": {"Content-Type": "application/json"}},
            {"content": b'{"title": "x"}', "headers": {"Content-Type": "text/plain"}},
            {},
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertFieldErrors(self.client.post(URL, **case), [("body", "invalid_body")])

    def test_every_error_is_reported_at_once(self) -> None:
        response = self.client.post(URL, json={"title": "", "category": "nope", "status": "resolved", "extra": 1})
        self.assertFieldErrors(
            response,
            [
                ("title", "blank"),
                ("description", "missing"),
                ("category", "invalid_choice"),
                ("status", "invalid_choice"),
                ("origin", "missing"),
                ("branch", "missing"),
                ("extra", "unknown_field"),
            ],
        )

    def test_messages_never_repeat_the_received_value(self) -> None:
        body = {"title": LEAK * 20, "description": "ok", "category": LEAK, "origin": LEAK, "branch": LEAK, "status": LEAK, LEAK: LEAK}
        response = self.client.post(URL, json=body)
        self.assertEqual(response.status_code, 400)
        for error in response.json()["detail"]:
            self.assertNotIn("leak", error["message"])
        # El único sitio donde aparece es `field` de la clave desconocida (identifica el campo).
        self.assertEqual(response.text.count("leak"), 1)

    def test_invalid_requests_write_nothing(self) -> None:
        self.client.post(URL, json=without("branch"))
        self.client.post(URL, content=b"nope", headers={"Content-Type": "application/json"})
        self.assertEqual(self.client.get(URL).json(), [])


class ListTests(IncidentApiTestCase):
    def test_empty_database(self) -> None:
        response = self.client.get(URL)
        self.assertEqual((response.status_code, response.json()), (200, []))
        self.assertFalse(self.db_path.exists())

    def test_filters(self) -> None:
        clock = FakeClock(datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
        self.client.app.state.incident_repository = IncidentRepository(self.db_path, clock=clock)  # type: ignore[attr-defined]
        created = []
        for origin, branch, category in (
            ("customer", "central", "client_complaint"),
            ("branch", "miami_office", "technical_failure"),
            ("branch", "remote", "technical_failure"),
            ("internal", "valencia_operations", "sla_breach"),
        ):
            clock.advance(minutes=1)
            created.append(self.create(origin=origin, branch=branch, category=category)["id"])
        self.patch_status(created[1], IN_PROGRESS)

        def ids(query: str) -> list[str]:
            response = self.client.get(f"{URL}{query}")
            self.assertEqual(response.status_code, 200)
            return [incident["id"] for incident in response.json()]

        self.assertEqual(ids(""), list(reversed(created)))
        self.assertEqual(ids("?status=in_progress"), [created[1]])
        self.assertEqual(ids("?origin=branch"), [created[2], created[1]])
        self.assertEqual(ids("?branch=remote"), [created[2]])
        self.assertEqual(ids("?category=sla_breach"), [created[3]])
        self.assertEqual(ids("?origin=branch&category=technical_failure&status=open"), [created[2]])
        self.assertEqual(ids("?branch=central&category=sla_breach"), [])

    def test_invalid_filter_values(self) -> None:
        for field in ("status", "origin", "branch", "category"):
            for value in ("nope", "", "OPEN"):
                with self.subTest(field=field, value=value):
                    self.assertFieldErrors(self.client.get(URL, params={field: value}), [(field, "invalid_choice")])

    def test_several_invalid_filters(self) -> None:
        response = self.client.get(URL, params={"status": "x", "branch": "y", "origin": "customer"})
        self.assertFieldErrors(response, [("status", "invalid_choice"), ("branch", "invalid_choice")])


class SummaryTests(IncidentApiTestCase):
    def test_empty_database_has_every_key_at_zero(self) -> None:
        response = self.client.get(SUMMARY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "total": 0,
                "by_status": {status.value: 0 for status in IncidentStatus},
                "by_category": {category.value: 0 for category in IncidentCategory},
                "by_origin": {origin.value: 0 for origin in IncidentOrigin},
                "by_branch": {branch.value: 0 for branch in Branch},
            },
        )
        self.assertFalse(self.db_path.exists())

    def test_after_the_seed_of_the_acceptance_fixture(self) -> None:
        self.seed_fixture()
        summary = self.client.get(SUMMARY_URL).json()
        self.assertEqual(summary["total"], 96)
        self.assertEqual(summary["by_status"], {"open": 27, "in_progress": 0, "resolved": 56, "discarded": 13})
        expected_categories = {category.value: 0 for category in IncidentCategory}
        expected_categories.update({"technical_failure": 49, "process_error": 35, "client_complaint": 12})
        self.assertEqual(summary["by_category"], expected_categories)
        self.assertEqual(summary["by_origin"], {"customer": 96, "branch": 0, "internal": 0})
        self.assertEqual(summary["by_branch"], {"central": 96, "valencia_operations": 0, "miami_office": 0, "remote": 0})

    def test_reflects_creations_and_status_changes(self) -> None:
        incident = self.create(origin="branch", branch="remote", category="data_quality")
        self.patch_status(incident["id"], DISCARDED)
        summary = self.client.get(SUMMARY_URL).json()
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["by_status"]["discarded"], 1)
        self.assertEqual(summary["by_origin"]["branch"], 1)
        self.assertEqual(summary["by_branch"]["remote"], 1)
        self.assertEqual(summary["by_category"]["data_quality"], 1)


class DetailTests(IncidentApiTestCase):
    def test_existing_incident(self) -> None:
        incident = self.create()
        response = self.client.get(f"{URL}/{incident['id']}")
        self.assertEqual((response.status_code, response.json()), (200, incident))

    def test_unknown_id(self) -> None:
        response = self.client.get(f"{URL}/{uuid4()}")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "incident not found", "code": "incident_not_found"})

    def test_id_that_is_not_a_uuid(self) -> None:
        for raw in ("123", "not-a-uuid", "3f2b6c1e-8a4d-4c2b-9f1e-1234567890a"):
            with self.subTest(raw=raw):
                response = self.client.get(f"{URL}/{raw}")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(response.json()["code"], "not_found")


class StatusChangeTests(IncidentApiTestCase):
    def incident_in(self, status: str) -> str:
        incident_id = self.create()["id"]
        for step in PATH_TO[status]:
            self.assertEqual(self.patch_status(incident_id, step).status_code, 200)
        return incident_id

    def test_all_16_transitions(self) -> None:
        self.assertEqual(set(TRANSITIONS), set(itertools.product(PATH_TO, repeat=2)))
        for (current, target), allowed in TRANSITIONS.items():
            with self.subTest(current=current, target=target):
                incident_id = self.incident_in(current)
                before = self.client.get(f"{URL}/{incident_id}").json()
                response = self.patch_status(incident_id, target)
                if allowed:
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["status"], target)
                else:
                    self.assertFieldErrors(response, [("status", "invalid_transition")], code="invalid_status_transition")
                    self.assertEqual(self.client.get(f"{URL}/{incident_id}").json(), before)

    def test_transition_message(self) -> None:
        incident_id = self.incident_in(RESOLVED)
        response = self.patch_status(incident_id, OPEN)
        self.assertEqual(
            response.json(),
            {
                "detail": [{"field": "status", "error": "invalid_transition", "message": "status resolved is final and cannot change"}],
                "code": "invalid_status_transition",
            },
        )

    def test_only_status_and_updated_at_change(self) -> None:
        clock = FakeClock(datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
        self.client.app.state.incident_repository = IncidentRepository(self.db_path, clock=clock)  # type: ignore[attr-defined]
        incident = self.create()
        clock.advance(hours=2)
        updated = self.patch_status(incident["id"], IN_PROGRESS).json()
        self.assertEqual(updated["status"], IN_PROGRESS)
        self.assertEqual(updated["updated_at"], "2026-10-07T11:00:00Z")
        self.assertEqual(updated["created_at"], incident["created_at"])
        for field in ("id", "title", "description", "category", "origin", "branch"):
            self.assertEqual(updated[field], incident[field])

    def test_body_without_status(self) -> None:
        incident_id = self.create()["id"]
        for body in ({}, {"status": None}):
            with self.subTest(body=body):
                response = self.client.patch(f"{URL}/{incident_id}/status", json=body)
                self.assertFieldErrors(response, [("status", "missing")])

    def test_invalid_status_value(self) -> None:
        incident_id = self.create()["id"]
        for value in ("closed", "IN_PROGRESS", 1, ""):
            with self.subTest(value=value):
                self.assertFieldErrors(self.patch_status(incident_id, value), [("status", "invalid_choice")])

    def test_other_fields_cannot_change(self) -> None:
        incident_id = self.create()["id"]
        response = self.client.patch(f"{URL}/{incident_id}/status", json={"status": IN_PROGRESS, "title": "Other"})
        self.assertFieldErrors(response, [("title", "unknown_field")])
        self.assertEqual(self.client.get(f"{URL}/{incident_id}").json()["status"], OPEN)

    def test_body_that_is_not_a_json_object(self) -> None:
        incident_id = self.create()["id"]
        for content in (b"nope", b'["in_progress"]', b""):
            with self.subTest(content=content):
                response = self.client.patch(
                    f"{URL}/{incident_id}/status", content=content, headers={"Content-Type": "application/json"}
                )
                self.assertFieldErrors(response, [("body", "invalid_body")])

    def test_unknown_or_malformed_id(self) -> None:
        response = self.patch_status(str(uuid4()), IN_PROGRESS)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "incident_not_found"))
        response = self.patch_status("not-a-uuid", IN_PROGRESS)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))


class AuthenticationTests(unittest.TestCase):
    def test_every_route_requires_a_token(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        client = managed_client(self, Settings(incidents_db_path=Path(directory.name) / "i.json"), authenticated=False)
        incident_id = str(uuid4())
        requests = [
            ("POST", URL, valid_incident()),
            ("GET", URL, None),
            ("GET", SUMMARY_URL, None),
            ("GET", f"{URL}/{incident_id}", None),
            ("PATCH", f"{URL}/{incident_id}/status", {"status": IN_PROGRESS}),
        ]
        for method, url, body in requests:
            with self.subTest(method=method, url=url):
                response = client.request(method, url, json=body)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["code"], "not_authenticated")
                self.assertEqual(response.headers["WWW-Authenticate"], "Bearer")
        self.assertFalse((Path(directory.name) / "i.json").exists())

    def test_invalid_token(self) -> None:
        client = managed_client(self, authenticated=False)
        client.headers["Authorization"] = "Bearer not-a-token"
        self.assertEqual(client.get(SUMMARY_URL).status_code, 401)


class NoRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = managed_client(self)

    def test_analyzer_routes_keep_their_405(self) -> None:
        for method, url, allowed in (("GET", ANALYZE_URL, "POST"), ("POST", EXPORT_URL, "GET")):
            with self.subTest(method=method, url=url):
                response = self.client.request(method, url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.headers["Allow"], allowed)
                self.assertEqual(response.json(), {"detail": "Method Not Allowed", "code": "method_not_allowed"})

    def test_unknown_path_is_still_404(self) -> None:
        response = self.client.get(f"{URL}/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found", "code": "not_found"})

    def test_suppliers_and_auth_keep_422(self) -> None:
        for method, url in (("POST", "/suppliers"), ("POST", "/users"), ("PUT", "/profiles/me")):
            with self.subTest(url=url):
                response = self.client.request(method, url, json={"unexpected": 1})
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "validation_error")
                self.assertIn("loc", response.json()["detail"][0])
        response = self.client.get("/suppliers", params={"country": "Nowhere"})
        self.assertEqual(response.status_code, 422)


class ExplodingRepository:
    def __getattr__(self, name: str) -> Any:
        def explode(*args: Any, **kwargs: Any) -> NoReturn:
            raise RuntimeError(f"unexpected failure while reading {LEAK}")

        return explode


class UnexpectedErrorTests(unittest.TestCase):
    def test_exception_in_every_new_route_is_an_opaque_500(self) -> None:
        client = managed_client(self)
        client.app.dependency_overrides[get_incident_repository] = ExplodingRepository  # type: ignore[attr-defined]
        incident_id = str(uuid4())
        requests = [
            ("POST", URL, valid_incident()),
            ("GET", URL, None),
            ("GET", SUMMARY_URL, None),
            ("GET", f"{URL}/{incident_id}", None),
            ("PATCH", f"{URL}/{incident_id}/status", {"status": IN_PROGRESS}),
        ]
        for method, url, body in requests:
            with self.subTest(method=method, url=url), capture_logs() as logs:
                response = client.request(method, url, json=body)
                self.assertEqual(response.status_code, 500)
                self.assertEqual(response.json(), {"detail": INTERNAL_ERROR_DETAIL, "code": "internal_error"})
                for leaked in (LEAK, "RuntimeError", "Traceback", "unexpected failure", "repository"):
                    self.assertNotIn(leaked, response.text)
                self.assertNotIn(LEAK, logs.text())
                self.assertNotIn("Traceback", logs.text())


class OpenApiTests(unittest.TestCase):
    def test_routes_are_documented(self) -> None:
        paths = managed_client(self).get("/openapi.json").json()["paths"]
        self.assertEqual(set(paths[URL]), {"get", "post"})
        self.assertEqual(set(paths[SUMMARY_URL]), {"get"})
        self.assertEqual(set(paths[f"{URL}/{{incident_id}}"]), {"get"})
        self.assertEqual(set(paths[f"{URL}/{{incident_id}}/status"]), {"patch"})
        status_filter = next(p for p in paths[URL]["get"]["parameters"] if p["name"] == "status")
        self.assertEqual(status_filter["schema"]["enum"], [status.value for status in IncidentStatus])


if __name__ == "__main__":
    unittest.main()
