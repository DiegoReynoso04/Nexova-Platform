"""Utilidades de los tests de AUTH-01 (usuarios, perfiles, login y JWT).

Cada test usa su propia base TinyDB temporal (nunca services/api/data/) y
solo emails ficticios `example.invalid`. Las contraseñas de test se generan al
vuelo: no hay ninguna fija en el repositorio.
"""

import json
import secrets
import tempfile
import unittest
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response

from app.auth.models import UserCreate, UserRole
from app.auth.service import UserService
from app.core.config import Settings
from app.main import create_app

from .support import TEST_DATABASE_URL, TEST_JWT_SECRET, TEST_TOKEN_MINUTES

USERS_URL = "/users"
LOGIN_URL = "/auth/login"
AUTH_ME_URL = "/auth/me"
PROFILE_ME_URL = "/profiles/me"
CREDENTIAL_KEYS = {"password", "hashed_password"}


def new_password() -> str:
    return secrets.token_urlsafe(12)


def all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for item in value.values() for key in all_keys(item)}
    if isinstance(value, list):
        return {key for item in value for key in all_keys(item)}
    return set()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class AuthTestCase(unittest.TestCase):
    """App real con base temporal de usuarios y proveedores; sin token por defecto."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.auth_db_path = Path(self._tmp.name) / "auth.json"
        self.settings = Settings(
            suppliers_db_path=Path(self._tmp.name) / "suppliers.json",
            auth_db_path=self.auth_db_path,
            jwt_secret_key=TEST_JWT_SECRET,
            access_token_expire_minutes=TEST_TOKEN_MINUTES,
            database_url=TEST_DATABASE_URL,
        )
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)

    @property
    def service(self) -> UserService:
        service = self.app.state.user_service
        assert isinstance(service, UserService)
        return service

    def register(self, email: str, password: str, **extra: Any) -> Response:
        return self.client.post(USERS_URL, json={"email": email, "password": password, **extra})

    def create_user(self, email: str, role: UserRole = UserRole.USER, **profile: Any) -> tuple[str, str]:
        """Registra un usuario (vía API si es `user`) y devuelve `(id, password)`."""
        password = new_password()
        if role == UserRole.USER:
            response = self.register(email, password, **profile)
            self.assertEqual(response.status_code, 201, response.text)
            return response.json()["id"], password
        user, _ = self.service.create_user(UserCreate(email=email, password=password, **profile), role=role)
        return str(user.id), password

    def login(self, email: str, password: str) -> Response:
        return self.client.post(LOGIN_URL, data={"username": email, "password": password})

    def token_for(self, email: str, password: str) -> str:
        response = self.login(email, password)
        self.assertEqual(response.status_code, 200, response.text)
        token: str = response.json()["access_token"]
        return token

    def user_with_token(self, email: str, role: UserRole = UserRole.USER, **profile: Any) -> tuple[str, str]:
        """Crea el usuario, hace login y devuelve `(id, token)`."""
        user_id, password = self.create_user(email, role, **profile)
        return user_id, self.token_for(email, password)

    def raw_db(self) -> dict[str, dict[str, dict[str, Any]]]:
        data: dict[str, dict[str, dict[str, Any]]] = json.loads(self.auth_db_path.read_text(encoding="utf-8"))
        return data

    def raw_users(self) -> list[dict[str, Any]]:
        return list(self.raw_db().get("users", {}).values())

    def raw_profiles(self) -> list[dict[str, Any]]:
        return list(self.raw_db().get("profiles", {}).values())

    def assertNoCredentials(self, response: Response) -> None:
        self.assertEqual(all_keys(response.json()) & CREDENTIAL_KEYS, set())
        self.assertNotIn("$2b$", response.text)

    def assertUnauthorized(self, response: Response) -> None:
        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["code"], "not_authenticated")
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def assertForbidden(self, response: Response) -> None:
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()["code"], "forbidden")
