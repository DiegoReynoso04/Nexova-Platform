"""AUTH-01: rutas existentes protegidas, rutas públicas, CORS y configuración del JWT."""

import dataclasses
import unittest
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import Response

from app.auth.models import UserRole
from app.auth.security import create_access_token
from app.core.config import MIN_JWT_SECRET_LENGTH, ConfigError, Settings
from app.main import create_app

from .auth_support import AuthTestCase, bearer, new_password
from .support import ANALYZE_URL, EXPORT_URL, FIXTURE, TEST_DATABASE_URL
from .suppliers_support import SUPPLIERS_URL, valid_supplier

# Las 8 rutas existentes con datos sensibles (incidentes con emails de clientes
# y el directorio de proveedores) que ahora exigen JWT.
PROTECTED_ROUTES: list[tuple[str, str]] = [
    ("POST", SUPPLIERS_URL),
    ("GET", SUPPLIERS_URL),
    ("GET", f"{SUPPLIERS_URL}/1"),
    ("PATCH", f"{SUPPLIERS_URL}/1/rate"),
    ("PATCH", f"{SUPPLIERS_URL}/1/status"),
    ("DELETE", f"{SUPPLIERS_URL}/1"),
    ("POST", ANALYZE_URL),
    ("GET", EXPORT_URL),
]


class ExistingRoutesProtectionTests(AuthTestCase):
    def call(self, method: str, url: str, headers: dict[str, str] | None = None) -> Response:
        """Petición con un cuerpo válido para cada ruta (el 401 no depende del cuerpo)."""
        kwargs: dict[str, Any] = {"headers": headers}
        if (method, url) == ("POST", SUPPLIERS_URL):
            kwargs["json"] = valid_supplier()
        elif url.endswith("/rate"):
            kwargs["json"] = {"monthly_rate": 900.0}
        elif url.endswith("/status"):
            kwargs["json"] = {"status": "suspended"}
        elif url == ANALYZE_URL:
            kwargs["files"] = {"file": ("incidents.csv", FIXTURE.read_bytes(), "text/csv")}
        return self.client.request(method, url, **kwargs)

    def test_existing_routes_without_token_are_401(self) -> None:  # [26]
        for method, url in PROTECTED_ROUTES:
            with self.subTest(route=f"{method} {url}"):
                self.assertUnauthorized(self.call(method, url))

    def test_existing_routes_with_invalid_or_expired_token_are_401(self) -> None:
        user_id, _ = self.create_user("alice@example.invalid")
        expired = create_access_token(self.settings, user_id, now=datetime.now(UTC) - timedelta(days=1))
        for token in ("not-a-jwt", expired):
            for method, url in PROTECTED_ROUTES:
                with self.subTest(route=f"{method} {url}", token=token[:10]):
                    self.assertUnauthorized(self.call(method, url, bearer(token)))

    def test_unauthenticated_requests_do_not_touch_data(self) -> None:
        self.assertUnauthorized(self.call("POST", SUPPLIERS_URL))
        _, token = self.user_with_token("alice@example.invalid")
        self.assertEqual(self.client.get(SUPPLIERS_URL, headers=bearer(token)).json(), [])
        self.assertEqual(self.client.get(EXPORT_URL, headers=bearer(token)).status_code, 404)  # sin análisis

    def test_existing_routes_work_with_a_valid_token(self) -> None:  # [27]
        _, token = self.user_with_token("alice@example.invalid")
        auth = bearer(token)
        expected = {
            ("POST", SUPPLIERS_URL): 201,
            ("GET", SUPPLIERS_URL): 200,
            ("GET", f"{SUPPLIERS_URL}/1"): 200,
            ("PATCH", f"{SUPPLIERS_URL}/1/rate"): 200,
            ("PATCH", f"{SUPPLIERS_URL}/1/status"): 200,
            ("DELETE", f"{SUPPLIERS_URL}/1"): 204,
            ("POST", ANALYZE_URL): 200,
            ("GET", EXPORT_URL): 200,
        }
        self.assertEqual(list(expected), PROTECTED_ROUTES)
        for (method, url), status in expected.items():  # en orden: alta → consultas → cambios → borrado
            with self.subTest(route=f"{method} {url}"):
                response = self.call(method, url, auth)
                self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(self.client.get(f"{SUPPLIERS_URL}/1", headers=auth).status_code, 404)  # borrado de verdad

    def test_any_role_can_use_existing_routes(self) -> None:
        # Sin permisos por rol en esta entrega: basta un token válido.
        for role in UserRole:
            with self.subTest(role=role):
                _, token = self.user_with_token(f"{role.value}@example.invalid", role)
                self.assertEqual(self.client.get(SUPPLIERS_URL, headers=bearer(token)).status_code, 200)


class PublicRoutesTests(AuthTestCase):
    def test_health_docs_and_openapi_are_public(self) -> None:
        for url in ("/health", "/docs", "/openapi.json"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_register_and_login_are_public(self) -> None:
        password = new_password()
        self.assertEqual(self.register("alice@example.invalid", password).status_code, 201)
        self.assertEqual(self.login("alice@example.invalid", password).status_code, 200)

    def test_openapi_declares_the_oauth2_password_flow(self) -> None:
        schema = self.client.get("/openapi.json").json()
        [scheme] = schema["components"]["securitySchemes"].values()
        self.assertEqual(scheme["type"], "oauth2")
        self.assertEqual(scheme["flows"]["password"]["tokenUrl"], "/auth/login")
        paths = schema["paths"]
        self.assertIn("security", paths["/suppliers"]["get"])
        self.assertIn("security", paths["/api/incidents/analyze"]["post"])
        self.assertNotIn("security", paths["/users"]["post"])
        self.assertNotIn("security", paths["/auth/login"]["post"])
        self.assertNotIn("security", paths["/health"]["get"])


class CorsAuthorizationTests(AuthTestCase):
    def test_preflight_allows_the_authorization_header(self) -> None:
        response = self.client.options(
            SUPPLIERS_URL,
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("authorization", response.headers["access-control-allow-headers"].lower())
        self.assertNotIn("access-control-allow-credentials", response.headers)


class AuthConfigTests(unittest.TestCase):
    def valid(self, **changes: Any) -> Settings:
        base = Settings(
            jwt_secret_key="k" * MIN_JWT_SECRET_LENGTH, access_token_expire_minutes=30, database_url=TEST_DATABASE_URL
        )
        return dataclasses.replace(base, **changes)

    def test_app_does_not_start_without_jwt_secret(self) -> None:
        for secret in ("", "k" * (MIN_JWT_SECRET_LENGTH - 1)):
            with self.subTest(length=len(secret)), self.assertRaises(ConfigError) as error:
                create_app(self.valid(jwt_secret_key=secret))
            self.assertIn("JWT_SECRET_KEY", str(error.exception))

    def test_app_does_not_start_without_token_expiration(self) -> None:
        with self.assertRaises(ConfigError) as error:
            create_app(self.valid(access_token_expire_minutes=None))
        self.assertIn("ACCESS_TOKEN_EXPIRE_MINUTES", str(error.exception))

    def test_reads_jwt_settings_from_environment(self) -> None:
        secret = "s" * 40
        settings = Settings.from_env(
            {"JWT_SECRET_KEY": secret, "ACCESS_TOKEN_EXPIRE_MINUTES": "45", "AUTH_DB_PATH": "custom/auth.json"}
        )
        self.assertEqual(settings.jwt_secret_key, secret)
        self.assertEqual(settings.access_token_expire_minutes, 45)
        self.assertEqual(settings.auth_db_path.as_posix(), "custom/auth.json")
        settings.require_auth()
        self.assertNotIn(secret, repr(settings))

    def test_environment_without_jwt_settings_fails_at_startup(self) -> None:
        settings = Settings.from_env({})
        self.assertEqual(settings.jwt_secret_key, "")
        self.assertIsNone(settings.access_token_expire_minutes)
        with self.assertRaises(ConfigError):
            create_app(settings)

    def test_invalid_expiration_is_rejected(self) -> None:
        for value in ("abc", "0", "-5", "1.5"):
            with self.subTest(value=value), self.assertRaises(ConfigError):
                Settings.from_env({"ACCESS_TOKEN_EXPIRE_MINUTES": value})


if __name__ == "__main__":
    unittest.main()
