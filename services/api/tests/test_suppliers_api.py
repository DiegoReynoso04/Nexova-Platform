"""Directorio de proveedores: validación (422), endpoints, filtros, 404 y `updated_at`."""

import json
from datetime import datetime

from app.models import VALID_CATEGORIES, VALID_STATUSES, SupplierCreate, SupplierRead

from .suppliers_support import SUPPLIERS_URL, SupplierTestCase, context_definitions, valid_supplier


class ModelMatchesContextTests(SupplierTestCase):
    def test_categories_and_statuses_are_exactly_the_context_ones(self) -> None:
        context = context_definitions()
        self.assertEqual(VALID_CATEGORIES, context["VALID_CATEGORIES"])
        self.assertEqual(VALID_STATUSES, context["VALID_STATUSES"])

    def test_response_has_exactly_the_context_fields_plus_id(self) -> None:
        body = self.create()
        self.assertEqual(
            set(body),
            {
                "id",
                "name",
                "country",
                "categories",
                "monthly_rate",
                "currency",
                "updated_at",
                "status",
                "contract_renewal_date",
                "contact_email",
                "notes",
            },
        )


class ResponseSchemaTests(SupplierTestCase):
    """Auditoría de serialización (D4): la salida tiene su propio esquema, no el de la entrada."""

    def test_response_schema_is_not_the_input_schema(self) -> None:
        self.assertFalse(issubclass(SupplierRead, SupplierCreate))
        operations = self.client.get("/openapi.json").json()["paths"]
        ok = {("post", ""): "201", ("get", ""): "200", ("get", "/{supplier_id}"): "200",
              ("patch", "/{supplier_id}/rate"): "200", ("patch", "/{supplier_id}/status"): "200"}
        for (method, suffix), status in ok.items():
            with self.subTest(method=method, path=suffix):
                schema = operations[SUPPLIERS_URL + suffix][method]["responses"][status]["content"]["application/json"]["schema"]
                self.assertIn("#/components/schemas/SupplierRead", json.dumps(schema))

    def test_a_stored_document_that_breaks_an_input_rule_is_still_listed(self) -> None:
        # Las reglas de entrada (moneda por país) no se ejecutan al leer: antes, un
        # documento así convertía todo `GET /suppliers` en un 500.
        created = self.create()
        data = json.loads(self.db_path.read_text(encoding="utf-8"))
        data["suppliers"][str(created["id"])]["currency"] = "USD" if created["currency"] == "EUR" else "EUR"
        self.db_path.write_text(json.dumps(data), encoding="utf-8")
        response = self.client.get(SUPPLIERS_URL)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()], [created["id"]])


class ValidationTests(SupplierTestCase):
    def assert_rejected(self, payload: dict[str, object]) -> None:
        response = self.client.post(SUPPLIERS_URL, json=payload)
        self.assertEqual(response.status_code, 422, response.text)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        for error in body["detail"]:
            self.assertEqual(set(error), {"loc", "msg", "type"})
        # Rechazado antes de tocar TinyDB: ni siquiera se crea el archivo.
        self.assertFalse(self.db_path.exists())

    def test_missing_required_fields(self) -> None:
        for field in ("name", "country", "categories", "monthly_rate", "currency", "status"):
            with self.subTest(field=field):
                payload = valid_supplier()
                del payload[field]
                self.assert_rejected(payload)

    def test_blank_name(self) -> None:
        self.assert_rejected(valid_supplier(name="   "))

    def test_country_outside_spain_usa(self) -> None:
        for country in ("France", "spain", "", None):
            with self.subTest(country=country):
                self.assert_rejected(valid_supplier(country=country))

    def test_status_outside_active_suspended(self) -> None:
        for status in ("inactive", "ACTIVE", "", None):
            with self.subTest(status=status):
                self.assert_rejected(valid_supplier(status=status))

    def test_monthly_rate_must_be_positive_number(self) -> None:
        for rate in (0, 0.0, -1, -0.01, "100", None, True):
            with self.subTest(rate=rate):
                self.assert_rejected(valid_supplier(monthly_rate=rate))

    def test_integer_rate_is_accepted(self) -> None:
        self.assertEqual(self.create(monthly_rate=250)["monthly_rate"], 250.0)

    def test_currency_must_match_country(self) -> None:
        self.assert_rejected(valid_supplier(country="Spain", currency="USD"))
        self.assert_rejected(valid_supplier(country="USA", currency="EUR"))
        self.assert_rejected(valid_supplier(currency="GBP"))

    def test_categories_must_be_valid_and_non_empty(self) -> None:
        self.assert_rejected(valid_supplier(categories=[]))
        self.assert_rejected(valid_supplier(categories=["catering"]))
        self.assert_rejected(valid_supplier(categories=["job_boards", "catering"]))
        self.assert_rejected(valid_supplier(categories="job_boards"))

    def test_renewal_date_must_be_yyyy_mm_dd(self) -> None:
        for value in ("31/03/2025", "2025-3-1", "2025-02-30", "2025-13-01", "20250331", ""):
            with self.subTest(value=value):
                self.assert_rejected(valid_supplier(contract_renewal_date=value))

    def test_system_fields_cannot_be_sent(self) -> None:
        self.assert_rejected(valid_supplier(updated_at="2026-01-01T00:00:00Z"))
        self.assert_rejected(valid_supplier(id=99))
        self.assert_rejected(valid_supplier(unknown_field="x"))


class CreateTests(SupplierTestCase):
    def test_created_with_id_and_system_timestamp(self) -> None:
        body = self.create(
            country="USA",
            currency="USD",
            categories=["ats_software", "video_interview"],
            contract_renewal_date="2026-10-15",
            contact_email="account@example.invalid",
            notes="Synthetic note",
        )
        self.assertIsInstance(body["id"], int)
        self.assertEqual(datetime.fromisoformat(body["updated_at"]), self.clock.now)
        self.assertEqual(body["categories"], ["ats_software", "video_interview"])
        self.assertEqual(body["contract_renewal_date"], "2026-10-15")
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{body['id']}").json(), body)

    def test_optional_fields_default_to_null(self) -> None:
        body = self.create()
        self.assertIsNone(body["contract_renewal_date"])
        self.assertIsNone(body["contact_email"])
        self.assertIsNone(body["notes"])

    def test_ids_are_unique(self) -> None:
        first, second = self.create(name="A"), self.create(name="B")
        self.assertNotEqual(first["id"], second["id"])


class ListAndFilterTests(SupplierTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.seed()

    def names(self, query: str = "") -> set[str]:
        response = self.client.get(f"{SUPPLIERS_URL}{query}")
        self.assertEqual(response.status_code, 200, response.text)
        return {supplier["name"] for supplier in response.json()}

    def test_empty_directory_returns_empty_list(self) -> None:
        self.db_path.unlink()
        self.assertEqual(self.client.get(SUPPLIERS_URL).json(), [])

    def test_without_filters_returns_all(self) -> None:
        self.assertEqual(len(self.names()), 15)

    def test_filter_by_country(self) -> None:
        spain, usa = self.names("?country=Spain"), self.names("?country=USA")
        self.assertEqual(len(spain), 8)
        self.assertEqual(len(usa), 7)
        self.assertIn("Workable", spain)
        self.assertIn("Greenhouse", usa)
        self.assertFalse(spain & usa)

    def test_filter_by_category(self) -> None:
        self.assertEqual(
            self.names("?category=job_boards"), {"LinkedIn Talent Solutions", "InfoJobs Premium", "Indeed Sponsored"}
        )
        self.assertEqual(self.names("?category=ats_software"), {"Workable", "Greenhouse"})

    def test_filter_matches_any_of_the_supplier_categories(self) -> None:
        self.create(name="Multi", categories=["training_platforms", "assessment_tools"])
        self.assertIn("Multi", self.names("?category=assessment_tools"))
        self.assertIn("Multi", self.names("?category=training_platforms"))

    def test_filters_combine(self) -> None:
        self.assertEqual(self.names("?country=USA&category=job_boards"), {"Indeed Sponsored"})
        self.assertEqual(self.names("?country=Spain&category=background_check"), set())

    def test_invalid_filter_values_are_rejected(self) -> None:
        for query in ("?country=France", "?category=catering"):
            with self.subTest(query=query):
                response = self.client.get(f"{SUPPLIERS_URL}{query}")
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json()["code"], "validation_error")


class DetailAndNotFoundTests(SupplierTestCase):
    def assert_not_found(self, method: str, path: str, json: object = None) -> None:
        response = self.client.request(method, f"{SUPPLIERS_URL}/{path}", json=json)
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json(), {"detail": "supplier not found", "code": "supplier_not_found"})

    def test_unknown_id_returns_404_everywhere(self) -> None:
        self.create()
        self.assert_not_found("GET", "999")
        self.assert_not_found("PATCH", "999/rate", {"monthly_rate": 10})
        self.assert_not_found("PATCH", "999/status", {"status": "active"})
        self.assert_not_found("DELETE", "999")

    def test_non_numeric_id_is_422(self) -> None:
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/abc").status_code, 422)


class RateUpdateTests(SupplierTestCase):
    def test_rate_update_records_timestamp(self) -> None:
        supplier = self.create(monthly_rate=100)
        changed_at = self.clock.advance(days=3, minutes=5)
        response = self.client.patch(f"{SUPPLIERS_URL}/{supplier['id']}/rate", json={"monthly_rate": 125.5})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["monthly_rate"], 125.5)
        self.assertEqual(datetime.fromisoformat(body["updated_at"]), changed_at)
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{supplier['id']}").json(), body)
        # El resto del proveedor no cambia.
        self.assertEqual({**supplier, "monthly_rate": 125.5, "updated_at": body["updated_at"]}, body)

    def test_invalid_rates_are_rejected_and_nothing_changes(self) -> None:
        supplier = self.create(monthly_rate=100)
        self.clock.advance(days=1)
        for payload in ({"monthly_rate": 0}, {"monthly_rate": -5}, {"monthly_rate": "50"}, {}, {"rate": 50}):
            with self.subTest(payload=payload):
                response = self.client.patch(f"{SUPPLIERS_URL}/{supplier['id']}/rate", json=payload)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{supplier['id']}").json(), supplier)

    def test_updated_at_is_not_accepted_from_client(self) -> None:
        supplier = self.create()
        response = self.client.patch(
            f"{SUPPLIERS_URL}/{supplier['id']}/rate",
            json={"monthly_rate": 200, "updated_at": "2000-01-01T00:00:00Z"},
        )
        self.assertEqual(response.status_code, 422)


class StatusUpdateTests(SupplierTestCase):
    def test_suspend_and_reactivate_without_touching_updated_at(self) -> None:
        supplier = self.create(status="active")
        self.clock.advance(days=10)
        for status in ("suspended", "active"):
            with self.subTest(status=status):
                response = self.client.patch(f"{SUPPLIERS_URL}/{supplier['id']}/status", json={"status": status})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["status"], status)
                self.assertEqual(response.json()["updated_at"], supplier["updated_at"])

    def test_invalid_status_is_rejected(self) -> None:
        supplier = self.create()
        for payload in ({"status": "inactive"}, {"status": "deleted"}, {"status": None}, {}):
            with self.subTest(payload=payload):
                response = self.client.patch(f"{SUPPLIERS_URL}/{supplier['id']}/status", json=payload)
                self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{supplier['id']}").json()["status"], "active")


class DeleteTests(SupplierTestCase):
    def test_delete_removes_supplier(self) -> None:
        kept, removed = self.create(name="Kept"), self.create(name="Removed")
        response = self.client.delete(f"{SUPPLIERS_URL}/{removed['id']}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/{removed['id']}").status_code, 404)
        self.assertEqual([s["name"] for s in self.client.get(SUPPLIERS_URL).json()], [kept["name"]])
        self.assertEqual(self.client.delete(f"{SUPPLIERS_URL}/{removed['id']}").status_code, 404)


class CorsForSuppliersTests(SupplierTestCase):
    def test_patch_and_delete_preflight_from_backoffice(self) -> None:
        for method in ("PATCH", "DELETE"):
            with self.subTest(method=method):
                response = self.client.options(
                    f"{SUPPLIERS_URL}/1/status",
                    headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": method},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")
