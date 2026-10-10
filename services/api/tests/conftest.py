"""Fixtures de la batería de AUTH-088 (estilo pytest).

Los tests de esta batería prueban la lógica de autenticación sin TestClient:
llaman a los servicios, al repositorio, a la seguridad y a las funciones de
ruta directamente, con una TinyDB temporal real (`tmp_path`), un reloj
inyectado y un sender de email falso. Nunca usan services/api/data/.

Los tests `unittest` existentes no usan estas fixtures, salvo la huella de
`data/`, que se aplica a toda la sesión.
"""

import hashlib
import itertools
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from tinydb import Query, TinyDB

from app.auth.email import EmailMessage
from app.auth.models import ProfileFields, UserInDB, UserRole
from app.auth.repository import PROFILES_TABLE, AuthRepository
from app.auth.security import hash_password
from app.auth.service import UserService
from app.core.config import Settings
from app.core.storage import GuardedJSONStorage, Store

REAL_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOKEN_MINUTES = 30
CLOCK_START = datetime(2026, 10, 6, 9, 0, tzinfo=UTC)


def _data_fingerprint() -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(REAL_DATA_DIR.glob("*.json"))}


@pytest.fixture(scope="session", autouse=True)
def real_data_is_never_touched() -> Iterator[None]:
    """Falla la sesión si algún test (nuevo o existente) modifica services/api/data/*.json."""
    before = _data_fingerprint()
    yield
    assert _data_fingerprint() == before, "la suite ha modificado services/api/data/*.json"


class FakeClock:
    """Reloj fijo que solo avanza cuando el test lo pide."""

    def __init__(self, start: datetime = CLOCK_START) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@dataclass
class FakeEmailSender:
    """Guarda los mensajes en vez de enviarlos; si `error` está definido, lo lanza."""

    error: Exception | None = None
    messages: list[EmailMessage] = field(default_factory=list)

    def send(self, message: EmailMessage) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(message)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Configuración válida con todas las bases en `tmp_path` y una clave generada al vuelo."""
    return Settings(
        suppliers_db_path=tmp_path / "suppliers.json",
        auth_db_path=tmp_path / "auth.json",
        incidents_db_path=tmp_path / "incidents.json",
        jwt_secret_key=secrets.token_urlsafe(48),
        access_token_expire_minutes=TOKEN_MINUTES,
    )


@pytest.fixture
def auth_repo(settings: Settings, clock: FakeClock) -> AuthRepository:
    return AuthRepository(settings.auth_db_path, clock=clock)


@pytest.fixture
def service(auth_repo: AuthRepository) -> UserService:
    return UserService(auth_repo)


@pytest.fixture
def fake_sender() -> FakeEmailSender:
    return FakeEmailSender()


@pytest.fixture(scope="session")
def known_password() -> tuple[str, str]:
    """Contraseña generada y su hash bcrypt, calculado una sola vez por sesión (bcrypt es lento)."""
    password = secrets.token_urlsafe(12)
    return password, hash_password(password)


MakeUser = Callable[..., tuple[UserInDB, str]]


@pytest.fixture
def make_user(auth_repo: AuthRepository, known_password: tuple[str, str]) -> MakeUser:
    """Crea un usuario en la base temporal y devuelve `(usuario, contraseña en claro)`.

    Por defecto reutiliza el hash de la sesión; con `password=` se hashea esa
    contraseña. Los emails son ficticios (`example.invalid`).
    """
    counter = itertools.count(1)

    def _make(
        email: str | None = None,
        *,
        role: UserRole = UserRole.USER,
        active: bool = True,
        password: str | None = None,
        **profile: Any,
    ) -> tuple[UserInDB, str]:
        plain, hashed = known_password if password is None else (password, hash_password(password))
        user, _ = auth_repo.create_user(
            email=email or f"user{next(counter)}@example.invalid",
            hashed_password=hashed,
            role=role,
            profile=ProfileFields(**profile),
        )
        if not active:
            updated = auth_repo.update_user(str(user.id), {"is_active": False})
            assert updated is not None
            user = updated
        return user, plain

    return _make


@pytest.fixture
def drop_profile(auth_repo: AuthRepository) -> Callable[[str], None]:
    """Borra solo el perfil de un usuario: fabrica un estado que la API nunca produce."""

    def _drop(user_id: str) -> None:
        with TinyDB(auth_repo.path, storage=GuardedJSONStorage, store=Store.AUTH, encoding="utf-8") as db:
            db.table(PROFILES_TABLE).remove(Query().user_id == user_id)

    return _drop
