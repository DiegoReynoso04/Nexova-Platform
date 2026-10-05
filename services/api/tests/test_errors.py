"""Errores HTTP, límite de tamaño, configuración y CORS."""

import unittest
from collections.abc import Iterator
from tempfile import SpooledTemporaryFile
from unittest import mock

from app.core.config import DEFAULT_MAX_UPLOAD_BYTES, ConfigError, Settings

from .support import (
    ANALYZE_URL,
    BOUNDARY,
    EXPORT_URL,
    FIXTURE,
    HEADER,
    MULTIPART_HEADERS,
    chunked,
    csv_bytes,
    make_client,
    multipart_body,
    multipart_body_of_size,
    post_csv,
)


class InvalidCsvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()

    def assertInvalidCsv(self, content: bytes, detail_fragment: str) -> None:
        response = post_csv(self.client, content)
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["code"], "invalid_csv")
        self.assertIn(detail_fragment, body["detail"])

    def test_empty_file(self) -> None:
        self.assertInvalidCsv(b"", "empty")

    def test_missing_columns(self) -> None:
        self.assertInvalidCsv(b"ticket_id,date\r\nNXV-000001,2026-08-01\r\n", "missing required columns")

    def test_invalid_utf8(self) -> None:
        self.assertInvalidCsv(HEADER.encode() + "NXV-1,x,Caf\xe9\r\n".encode("latin-1"), "not valid UTF-8")

    def test_malformed_csv(self) -> None:
        # Un campo mayor que csv.field_size_limit() (128 KiB) hace fallar al lector.
        huge_field = '"' + "x" * 200_000 + '"'
        self.assertInvalidCsv(HEADER.encode() + huge_field.encode(), "malformed CSV")


class UnsupportedFileTypeTests(unittest.TestCase):
    def test_non_csv_extension_is_415(self) -> None:
        for filename in ("incidents.txt", "incidents.csv.txt", "incidents", "csv"):
            with self.subTest(filename=filename):
                response = post_csv(make_client(), FIXTURE.read_bytes(), filename=filename)
                self.assertEqual(response.status_code, 415)
                self.assertEqual(response.json(), {"detail": "only .csv files are accepted", "code": "unsupported_file_type"})

    def test_415_does_not_echo_filename(self) -> None:
        response = post_csv(make_client(), b"x", filename="leak@example.invalid.txt")
        self.assertNotIn("leak", response.text)


class SizeLimitTests(unittest.TestCase):
    def test_default_limit_is_one_mebibyte(self) -> None:
        self.assertEqual(DEFAULT_MAX_UPLOAD_BYTES, 1_048_576)
        self.assertEqual(Settings().max_upload_bytes, 1_048_576)

    def test_body_over_limit_with_content_length_is_413(self) -> None:
        response = post_csv(make_client(), b"a" * (DEFAULT_MAX_UPLOAD_BYTES + 1))
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "file_too_large")

    def test_body_over_limit_without_content_length_is_413(self) -> None:
        content = multipart_body(b"a" * 5_000)

        def chunks() -> Iterator[bytes]:
            for start in range(0, len(content), 1_000):
                yield content[start : start + 1_000]

        client = make_client(Settings(max_upload_bytes=2_000))
        response = client.post(
            ANALYZE_URL,
            content=chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "file_too_large")

    def test_limit_is_configurable(self) -> None:
        client = make_client(Settings(max_upload_bytes=500))
        self.assertEqual(post_csv(client, FIXTURE.read_bytes()).status_code, 413)
        self.assertEqual(post_csv(make_client(), FIXTURE.read_bytes()).status_code, 200)

    def test_body_under_limit_without_content_length_is_accepted(self) -> None:
        content = multipart_body(FIXTURE.read_bytes())
        response = make_client().post(
            ANALYZE_URL,
            content=iter([content]),
            headers={"Content-Type": f"multipart/form-data; boundary={BOUNDARY}"},
        )
        self.assertEqual(response.status_code, 200)


class ExactBodyLimitTests(unittest.TestCase):
    """El límite es del BODY HTTP completo (multipart incluido), no del CSV."""

    def post(self, body: bytes, *, stream: bool) -> tuple[int, dict]:  # type: ignore[type-arg]
        response = make_client().post(
            ANALYZE_URL, content=chunked(body) if stream else body, headers=MULTIPART_HEADERS
        )
        return response.status_code, response.json()

    def test_body_of_exactly_max_upload_bytes_is_accepted(self) -> None:
        body = multipart_body_of_size(DEFAULT_MAX_UPLOAD_BYTES)
        for stream in (False, True):
            with self.subTest(content_length=not stream):
                status, payload = self.post(body, stream=stream)
                self.assertEqual(status, 200)
                self.assertEqual(payload["totals"]["total_records"], 1)

    def test_body_of_max_upload_bytes_plus_one_is_413(self) -> None:
        body = multipart_body_of_size(DEFAULT_MAX_UPLOAD_BYTES + 1)
        for stream in (False, True):
            with self.subTest(content_length=not stream):
                status, payload = self.post(body, stream=stream)
                self.assertEqual(status, 413)
                self.assertEqual(payload["code"], "file_too_large")


class NoDiskSpoolingTests(unittest.TestCase):
    """Con el límite por defecto, Starlette nunca vuelca el upload (con PII) a disco.

    Solo datos sintéticos: una fila con email `example.invalid` y relleno.
    """

    def upload_and_count_rollovers(self, max_upload_bytes: int, body_size: int) -> tuple[int, int]:
        client = make_client(Settings(max_upload_bytes=max_upload_bytes))
        with mock.patch.object(
            SpooledTemporaryFile, "rollover", autospec=True, side_effect=SpooledTemporaryFile.rollover
        ) as rollover:
            response = client.post(ANALYZE_URL, content=multipart_body_of_size(body_size), headers=MULTIPART_HEADERS)
        return response.status_code, rollover.call_count

    def test_largest_accepted_body_never_rolls_over_to_disk(self) -> None:
        status, rollovers = self.upload_and_count_rollovers(DEFAULT_MAX_UPLOAD_BYTES, DEFAULT_MAX_UPLOAD_BYTES)
        self.assertEqual(status, 200)
        self.assertEqual(rollovers, 0)

    def test_spy_detects_rollover_above_one_mebibyte(self) -> None:
        # Control positivo: demuestra que el espía funciona. Con un límite mayor
        # (configuración no recomendada) el archivo sí pasa a disco.
        status, rollovers = self.upload_and_count_rollovers(3 * DEFAULT_MAX_UPLOAD_BYTES, 2 * DEFAULT_MAX_UPLOAD_BYTES)
        self.assertEqual(status, 200)
        self.assertGreater(rollovers, 0)


class ValidationErrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = make_client()

    def assertValidationError(self, response_json: dict) -> None:  # type: ignore[type-arg]
        self.assertEqual(response_json["code"], "validation_error")
        self.assertIsInstance(response_json["detail"], list)
        for error in response_json["detail"]:
            self.assertEqual(set(error) - {"loc", "msg", "type"}, set())
            self.assertNotIn("input", error)
            self.assertNotIn("ctx", error)
            self.assertNotIn("url", error)

    def test_missing_file_field(self) -> None:
        response = self.client.post(ANALYZE_URL)
        self.assertEqual(response.status_code, 422)
        self.assertValidationError(response.json())

    def test_wrong_field_name(self) -> None:
        response = self.client.post(ANALYZE_URL, files={"upload": ("incidents.csv", FIXTURE.read_bytes(), "text/csv")})
        self.assertEqual(response.status_code, 422)
        self.assertValidationError(response.json())
        self.assertEqual(response.json()["detail"][0]["loc"], ["body", "file"])

    def test_json_body(self) -> None:
        response = self.client.post(ANALYZE_URL, json={"file": "whatever"})
        self.assertEqual(response.status_code, 422)
        self.assertValidationError(response.json())

    def test_csv_sent_as_text_field_is_not_reflected(self) -> None:
        text = csv_bytes("NXV-000001,2026-08-01,Acme,TECHNICAL,Printer broken,AGT-01,OPEN,pasted@example.invalid,").decode()
        response = self.client.post(ANALYZE_URL, data={"file": text})
        self.assertEqual(response.status_code, 422)
        self.assertValidationError(response.json())
        self.assertNotIn("pasted@example.invalid", response.text)
        self.assertNotIn("Printer broken", response.text)


class MalformedMultipartTests(unittest.TestCase):
    def test_unparseable_multipart_is_400_without_parser_details(self) -> None:
        body = b'--other-boundary\r\nContent-Disposition: form-data; filename="x.csv"\r\n\r\nleak@example.invalid\r\n--other-boundary--\r\n'
        response = make_client().post(
            ANALYZE_URL,
            content=body,
            headers={"Content-Type": "multipart/form-data; boundary=other-boundary"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "Bad Request", "code": "bad_request"})


class GenericHttpErrorTests(unittest.TestCase):
    def test_unknown_route(self) -> None:
        response = make_client().get("/api/incidents/unknown")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "Not Found", "code": "not_found"})

    def test_wrong_method(self) -> None:
        response = make_client().get(ANALYZE_URL)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["code"], "method_not_allowed")

    def test_405_includes_allow_header(self) -> None:
        # RFC 9110: un 405 debe indicar los métodos permitidos.
        for method, url, allowed in (("GET", ANALYZE_URL, {"POST"}), ("POST", EXPORT_URL, {"GET"})):
            with self.subTest(method=method, url=url):
                response = make_client().request(method, url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual({m.strip() for m in response.headers["allow"].split(",")}, allowed)
                self.assertEqual(response.json(), {"detail": "Method Not Allowed", "code": "method_not_allowed"})


class ConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(settings.cors_allowed_origins, ("http://localhost:3000",))
        self.assertEqual(settings.max_upload_bytes, 1_048_576)

    def test_reads_environment(self) -> None:
        settings = Settings.from_env(
            {"CORS_ALLOWED_ORIGINS": "http://localhost:3000, http://localhost:3001 ,", "MAX_UPLOAD_BYTES": "2048"}
        )
        self.assertEqual(settings.cors_allowed_origins, ("http://localhost:3000", "http://localhost:3001"))
        self.assertEqual(settings.max_upload_bytes, 2048)

    def test_wildcard_origin_is_rejected(self) -> None:
        with self.assertRaises(ConfigError):
            Settings.from_env({"CORS_ALLOWED_ORIGINS": "*"})

    def test_invalid_max_upload_is_rejected(self) -> None:
        for value in ("abc", "0", "-5"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                Settings.from_env({"MAX_UPLOAD_BYTES": value})


class CorsTests(unittest.TestCase):
    def preflight(self, origin: str, method: str) -> dict[str, str]:
        response = make_client().options(
            ANALYZE_URL, headers={"Origin": origin, "Access-Control-Request-Method": method}
        )
        return dict(response.headers)

    def test_allowed_origin_and_method(self) -> None:
        headers = self.preflight("http://localhost:3000", "POST")
        self.assertEqual(headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertNotIn("access-control-allow-credentials", headers)

    def test_disallowed_origin(self) -> None:
        self.assertNotIn("access-control-allow-origin", self.preflight("http://evil.example", "POST"))

    def test_only_declared_methods_are_allowed(self) -> None:
        # GET/POST (incidentes y proveedores) + PATCH/DELETE (directorio de proveedores)
        # + PUT (perfil desde el frontend, AUTH-02). Cualquier otro método se rechaza.
        response = make_client().options(
            ANALYZE_URL, headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "TRACE"}
        )
        self.assertEqual(response.status_code, 400)
        allowed = {method.strip() for method in response.headers.get("access-control-allow-methods", "").split(",")}
        self.assertNotIn("TRACE", allowed)
        self.assertEqual({"GET", "POST", "PATCH", "PUT", "DELETE"}, allowed - {"OPTIONS", "HEAD"})

    def test_put_preflight_for_the_profile(self) -> None:
        # AUTH-02: PUT /profiles/me desde el navegador, con el JWT en Authorization.
        response = make_client().options(
            "/profiles/me",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PUT",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")
        self.assertIn("PUT", response.headers.get("access-control-allow-methods", ""))
        self.assertNotIn("access-control-allow-credentials", response.headers)

    def test_export_headers_are_exposed_to_the_browser(self) -> None:
        client = make_client()
        post_csv(client, FIXTURE.read_bytes())
        response = client.get("/api/incidents/results/export", headers={"Origin": "http://localhost:3000"})
        exposed = response.headers.get("access-control-expose-headers", "").lower()
        self.assertIn("x-analysis-id", exposed)
        self.assertIn("content-disposition", exposed)


if __name__ == "__main__":
    unittest.main()
