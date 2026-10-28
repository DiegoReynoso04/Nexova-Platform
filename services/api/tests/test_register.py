"""`POST /users` (registro público): qué datos crean una cuenta y cómo se guardan.

Unidades: la función de ruta `register_user` (`app/routes/users.py`),
`UserService.create_user` y las reglas de entrada de `UserCreate`
(`normalize_email`, `_check_password`, `ProfileFields`). Sin HTTP: las reglas
de entrada se prueban validando el modelo, que es lo que FastAPI convierte
en un 422.
"""

import secrets
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from tinydb import TinyDB

import app.auth.security as security
from app.auth.models import (
    ChangePasswordRequest,
    ResetPasswordRequest,
    UserCreate,
    UserRole,
    UserUpdate,
)
from app.auth.repository import PROFILES_TABLE, AuthRepository
from app.auth.security import verify_password
from app.auth.service import UserService
from app.core.errors import EmailAlreadyRegisteredError
from app.core.storage import GuardedJSONStorage, Store
from app.routes.users import register_user

from .conftest import FakeClock

DOMAIN = "@example.invalid"
# Generada al vuelo, como en el resto de la suite: ninguna contraseña fija en el repo.
VALID_PASSWORD = secrets.token_urlsafe(12)


def _rejected(model: type[BaseModel], data: dict[str, Any]) -> list[dict[str, Any]]:
    """Valida `data` contra `model`, exige que falle y devuelve los errores de Pydantic."""
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    return list(exc.value.errors())


def _rejected_fields(data: dict[str, Any]) -> set[str]:
    return {str(error["loc"][0]) for error in _rejected(UserCreate, data)}


def _signup(**overrides: Any) -> dict[str, Any]:
    return {"email": f"ana{DOMAIN}", "password": VALID_PASSWORD, **overrides}


def _profile_count(auth_repo: AuthRepository) -> int:
    with TinyDB(auth_repo.path, storage=GuardedJSONStorage, store=Store.AUTH, encoding="utf-8") as db:
        return len(db.table(PROFILES_TABLE))


# --- Camino feliz (R1) y normalización del email (R2) ---


def test_registration_creates_an_active_user_with_hashed_password_and_profile(
    service: UserService, auth_repo: AuthRepository, clock: FakeClock
) -> None:
    password = secrets.token_urlsafe(12)
    created = register_user(UserCreate(email=f"ana{DOMAIN}", password=password, name="Ana"), service)

    # La respuesta es solo la referencia (auditoría de serialización, D1): ni la
    # credencial ni el email que el cliente acaba de enviar.
    assert set(created.model_dump()) == {"id"}

    stored = auth_repo.get_user(str(created.id))
    assert stored is not None
    # D-AUTH-8: el registro público crea siempre `user`, activo.
    assert (stored.role, stored.is_active, stored.created_at) == (UserRole.USER, True, clock.now)
    assert stored.hashed_password != password
    assert verify_password(password, stored.hashed_password)

    profile = auth_repo.get_profile(str(created.id))
    assert profile is not None
    assert (profile.name, profile.phone, profile.address) == ("Ana", None, None)


def test_registration_stores_the_email_trimmed_and_lowercased(service: UserService, auth_repo: AuthRepository) -> None:
    # D-AUTH-6: un solo formato guardado, para que el login y la unicidad no dependan de mayúsculas.
    created = register_user(UserCreate(email="  Ana.Lopez@EXAMPLE.invalid ", password=VALID_PASSWORD), service)

    found = auth_repo.get_user_by_email("ana.lopez@example.invalid")
    assert found is not None and found.id == created.id


# --- Duplicados (R3) ---


def test_registration_with_an_already_used_email_fails_without_a_second_profile(
    service: UserService, auth_repo: AuthRepository
) -> None:
    register_user(UserCreate(email=f"ana{DOMAIN}", password=VALID_PASSWORD), service)

    for variant in (f"ana{DOMAIN}", f"ANA{DOMAIN.upper()}", f"  ana{DOMAIN}  "):
        with pytest.raises(EmailAlreadyRegisteredError):
            register_user(UserCreate(email=variant, password=VALID_PASSWORD), service)

    assert len(service.list_users()) == 1
    assert _profile_count(auth_repo) == 1


# --- Reglas de la contraseña (R4, R5 y el byte NUL) ---


@pytest.mark.parametrize(
    ("password", "accepted"),
    [
        pytest.param("a" * 7, False, id="7 caracteres"),
        pytest.param("a" * 8, True, id="8 caracteres"),
        pytest.param("a" * 72, True, id="72 bytes"),
        pytest.param("a" * 73, False, id="73 bytes"),
    ],
)
def test_password_needs_8_characters_and_at_most_72_bytes(password: str, accepted: bool) -> None:
    # D-AUTH-7: bcrypt solo usa 72 bytes; más se rechaza en vez de truncarse en silencio.
    if accepted:
        assert UserCreate.model_validate(_signup(password=password)).password == password
    else:
        assert _rejected_fields(_signup(password=password)) == {"password"}


@pytest.mark.parametrize(
    ("password", "accepted"),
    [
        pytest.param("ñ" * 36, True, id="ñ x36 = 72 bytes"),
        pytest.param("ñ" * 37, False, id="ñ x37 = 74 bytes"),
        pytest.param("😀" * 18, True, id="emoji x18 = 72 bytes"),
        pytest.param("😀" * 19, False, id="emoji x19 = 76 bytes"),
        pytest.param("ñ" * 7, False, id="ñ x7 = 7 caracteres"),
    ],
)
def test_password_limits_count_bytes_for_the_maximum_and_characters_for_the_minimum(password: str, accepted: bool) -> None:
    # El máximo es de bcrypt (bytes UTF-8); el mínimo es de la persona (caracteres):
    # 37 «ñ» son solo 37 caracteres pero 74 bytes, y 7 «ñ» siguen siendo 7 caracteres.
    if accepted:
        assert UserCreate.model_validate(_signup(password=password)).password == password
    else:
        assert _rejected_fields(_signup(password=password)) == {"password"}


@pytest.mark.parametrize(
    ("model", "data", "field"),
    [
        pytest.param(UserCreate, {"email": f"ana{DOMAIN}"}, "password", id="registro"),
        pytest.param(UserUpdate, {}, "password", id="PUT de un admin"),
        pytest.param(ResetPasswordRequest, {"token": "token-del-enlace"}, "new_password", id="reset"),
        pytest.param(ChangePasswordRequest, {"current_password": VALID_PASSWORD}, "new_password", id="change"),
    ],
)
def test_new_password_with_nul_byte_is_rejected_before_reaching_bcrypt(
    monkeypatch: pytest.MonkeyPatch, model: type[BaseModel], data: dict[str, Any], field: str
) -> None:
    # Bug encontrado por esta batería: bcrypt lanza una excepción con un NUL y la API
    # respondía 500. Ahora toda contraseña nueva lo rechaza al validar (422).
    bcrypt_calls: list[str] = []
    monkeypatch.setattr(security.bcrypt, "hash", lambda password, *args, **kwargs: bcrypt_calls.append(password))
    monkeypatch.setattr(security.bcrypt, "verify", lambda password, *args, **kwargs: bcrypt_calls.append(password))

    errors = _rejected(model, {**data, field: "abcd\x00efgh"})

    assert [(error["loc"], "NUL" in error["msg"]) for error in errors] == [((field,), True)]
    assert bcrypt_calls == []


# --- Email, campos y perfil (R6–R9) ---


@pytest.mark.parametrize(
    ("data", "field"),
    [
        pytest.param(_signup(email=""), "email", id="email vacío"),
        pytest.param(_signup(email="   "), "email", id="email solo espacios"),
        pytest.param(_signup(password=""), "password", id="contraseña vacía"),
    ],
)
def test_empty_email_or_password_is_rejected(data: dict[str, Any], field: str) -> None:
    assert _rejected_fields(data) == {field}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("role", "admin", id="role admin"),
        pytest.param("role", "user", id="role user"),
        pytest.param("hashed_password", "$2b$12$abc", id="hashed_password"),
        pytest.param("id", "00000000-0000-4000-8000-000000000000", id="id"),
        pytest.param("is_active", False, id="is_active"),
        pytest.param("user_id", "00000000-0000-4000-8000-000000000000", id="user_id"),
    ],
)
def test_registration_rejects_fields_the_backend_decides(field: str, value: object) -> None:
    # D-AUTH-8: el rol, la identidad, el estado y el hash los fija el backend; enviarlos
    # (incluso `role: user`) es un error, no algo que se ignora en silencio.
    errors = _rejected(UserCreate, _signup(**{field: value}))
    assert [(error["loc"], error["type"]) for error in errors] == [((field,), "extra_forbidden")]


def test_email_may_have_254_characters_but_not_255() -> None:
    # D-AUTH-6 (RFC 5321): 254 caracteres como máximo.
    at_limit = "a" * (254 - len(DOMAIN)) + DOMAIN
    assert len(at_limit) == 254
    assert UserCreate.model_validate(_signup(email=at_limit)).email == at_limit
    assert _rejected_fields(_signup(email="a" + at_limit)) == {"email"}


def test_profile_fields_are_trimmed_and_limited_to_200_characters(service: UserService, auth_repo: AuthRepository) -> None:
    # El límite se mide tras recortar los espacios: 200 caracteres útiles.
    assert _rejected_fields(_signup(name="a" * 201)) == {"name"}

    created = register_user(UserCreate.model_validate(_signup(name=f"  {'a' * 200}  ", address="  Calle Ejemplo 1 ")), service)

    profile = auth_repo.get_profile(str(created.id))
    assert profile is not None
    assert (profile.name, profile.address) == ("a" * 200, "Calle Ejemplo 1")
