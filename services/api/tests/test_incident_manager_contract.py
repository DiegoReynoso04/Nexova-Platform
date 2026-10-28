"""Contrato publicado del gestor de incidencias (auditoría de serialización, D5, D6 y D8).

Los modelos de entrada (`IncidentCreateRequest`, `IncidentStatusChangeRequest`)
son lo que OpenAPI publica; la autoridad de validación es `nexova_shared`. Estos
tests comprueban que los dos dicen lo mismo, que un campo no previsto sigue
respondiendo el 400 `unknown_field` de la Parte E y que OpenAPI documenta los
errores reales (400, no el 422 nativo de FastAPI).
"""

import tempfile
import unittest
from pathlib import Path
from typing import Any

from nexova_shared.incidents import (
    INITIAL_STATUS,
    INPUT_FIELDS,
    STATUS_CHANGE_FIELDS,
    TITLE_MAX_LENGTH,
    Branch,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    IncidentValidationError,
    validate_incident_fields,
    validate_status_change,
)

from app.core.config import Settings
from app.modules.incident_manager.models import IncidentCreateRequest, IncidentStatusChangeRequest

from .test_incident_manager_api import URL, managed_client, valid_incident

DETAIL_URL = f"{URL}/{{incident_id}}"
STATUS_URL = f"{URL}/{{incident_id}}/status"
DETAIL_KEYS = {"id", "title", "description", "category", "status", "origin", "branch", "created_at", "updated_at"}


def missing_fields(validate: Any) -> set[str]:
    """Campos que `nexova_shared` exige: los que reporta como `missing` con un cuerpo vacío."""
    try:
        validate({})
    except IncidentValidationError as error:
        return {item.field for item in error.errors if item.error.value == "missing"}
    raise AssertionError("an empty body must be invalid")


class ContractTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.client = managed_client(self, Settings(incidents_db_path=Path(directory.name) / "incidents.json"))
        self.openapi = self.client.get("/openapi.json").json()

    def request_schema(self, path: str, method: str) -> dict[str, Any]:
        operation = self.openapi["paths"][path][method]
        self.assertTrue(operation["requestBody"]["required"])
        schema: dict[str, Any] = operation["requestBody"]["content"]["application/json"]["schema"]
        return schema


class InputSchemaMatchesSharedRulesTests(ContractTestCase):
    def test_create_schema_has_exactly_the_fields_nexova_shared_accepts(self) -> None:
        self.assertEqual(set(IncidentCreateRequest.model_fields), set(INPUT_FIELDS))
        schema = self.request_schema(URL, "post")
        self.assertEqual(set(schema["properties"]), set(INPUT_FIELDS))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), missing_fields(validate_incident_fields))

    def test_status_change_schema_has_exactly_the_fields_nexova_shared_accepts(self) -> None:
        self.assertEqual(set(IncidentStatusChangeRequest.model_fields), set(STATUS_CHANGE_FIELDS))
        schema = self.request_schema(STATUS_URL, "patch")
        self.assertEqual(set(schema["properties"]), set(STATUS_CHANGE_FIELDS))
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), missing_fields(validate_status_change))
        self.assertEqual(schema["properties"]["status"]["enum"], [member.value for member in IncidentStatus])

    def test_create_schema_values_are_the_shared_vocabulary_and_limits(self) -> None:
        properties = self.request_schema(URL, "post")["properties"]
        for field, vocabulary in (("category", IncidentCategory), ("origin", IncidentOrigin), ("branch", Branch)):
            with self.subTest(field=field):
                self.assertEqual(properties[field]["enum"], [member.value for member in vocabulary])
        self.assertEqual(properties["title"]["maxLength"], TITLE_MAX_LENGTH)
        # Al crear, `status` es opcional y solo admite el estado inicial (P4-8).
        status_options = properties["status"]["anyOf"]
        self.assertIn({"const": INITIAL_STATUS.value, "type": "string"}, status_options)
        self.assertIn({"type": "null"}, status_options)

    def test_every_published_field_is_accepted_by_the_api(self) -> None:
        response = self.client.post(URL, json=valid_incident(status=INITIAL_STATUS.value))
        self.assertEqual(response.status_code, 201, response.text)


class UnknownFieldTests(ContractTestCase):
    def assert_unknown_field(self, response: Any, field: str) -> None:
        self.assertEqual(response.status_code, 400, response.text)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        self.assertIn({"field": field, "error": "unknown_field", "message": "this field is not accepted"}, body["detail"])

    def test_create_with_a_field_outside_the_contract_is_400_unknown_field(self) -> None:
        for field in ("id", "created_at", "updated_at", "priority"):
            with self.subTest(field=field):
                self.assert_unknown_field(self.client.post(URL, json=valid_incident(**{field: "x"})), field)

    def test_status_change_with_a_field_outside_the_contract_is_400_unknown_field(self) -> None:
        incident = self.client.post(URL, json=valid_incident()).json()
        url = STATUS_URL.format(incident_id=incident["id"])
        for field in ("title", "updated_at"):
            with self.subTest(field=field):
                response = self.client.patch(url, json={"status": IncidentStatus.IN_PROGRESS.value, field: "x"})
                self.assert_unknown_field(response, field)


class ResponseSchemaTests(ContractTestCase):
    def test_list_items_have_no_updated_at_but_the_detail_does(self) -> None:
        created = self.client.post(URL, json=valid_incident()).json()
        self.assertEqual(set(created), DETAIL_KEYS)
        [item] = self.client.get(URL).json()
        self.assertEqual(set(item), DETAIL_KEYS - {"updated_at"})
        self.assertEqual(set(self.client.get(DETAIL_URL.format(incident_id=created["id"])).json()), DETAIL_KEYS)

    def test_responses_use_the_read_schemas_not_the_stored_model(self) -> None:
        schemas = {
            (URL, "post", "201"): "IncidentRead",
            (URL, "get", "200"): "IncidentListItem",
            (DETAIL_URL, "get", "200"): "IncidentRead",
            (STATUS_URL, "patch", "200"): "IncidentRead",
        }
        for (path, method, status), name in schemas.items():
            with self.subTest(path=path, method=method):
                schema = self.openapi["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
                self.assertIn(f"#/components/schemas/{name}", str(schema))
        self.assertNotIn("Incident", self.openapi["components"]["schemas"])


class OpenApiErrorsTests(ContractTestCase):
    OPERATIONS = ((URL, "post"), (URL, "get"), (f"{URL}/summary", "get"), (DETAIL_URL, "get"), (STATUS_URL, "patch"))

    def test_no_route_documents_the_422_it_never_returns(self) -> None:
        for path, method in self.OPERATIONS:
            with self.subTest(path=path, method=method):
                responses = self.openapi["paths"][path][method]["responses"]
                self.assertNotIn("422", responses)
                self.assertTrue({"401", "503"} <= set(responses))

    def test_the_documented_400_is_the_real_one(self) -> None:
        for path, method in ((URL, "post"), (URL, "get"), (STATUS_URL, "patch")):
            with self.subTest(path=path, method=method):
                response = self.openapi["paths"][path][method]["responses"]["400"]["content"]["application/json"]
                self.assertEqual(response["schema"], {"$ref": "#/components/schemas/IncidentValidationErrorResponse"})
        example = self.openapi["paths"][URL]["post"]["responses"]["400"]["content"]["application/json"]["examples"]
        self.assertEqual(example["validation_error"]["value"], self.client.post(URL, json={}).json())

    def test_the_documented_transition_error_is_the_real_one(self) -> None:
        incident = self.client.post(URL, json=valid_incident()).json()
        url = STATUS_URL.format(incident_id=incident["id"])
        self.client.patch(url, json={"status": IncidentStatus.DISCARDED.value})
        real = self.client.patch(url, json={"status": INITIAL_STATUS.value})
        self.assertEqual(real.status_code, 400)
        examples = self.openapi["paths"][STATUS_URL]["patch"]["responses"]["400"]["content"]["application/json"]["examples"]
        self.assertEqual(examples["invalid_status_transition"]["value"], real.json())

    def test_the_rest_of_the_api_keeps_its_422(self) -> None:
        # Solo el gestor cambia: proveedores y auth siguen validando con 422.
        self.assertIn("422", self.openapi["paths"]["/suppliers"]["post"]["responses"])
        self.assertIn("422", self.openapi["paths"]["/users"]["post"]["responses"])


if __name__ == "__main__":
    unittest.main()
