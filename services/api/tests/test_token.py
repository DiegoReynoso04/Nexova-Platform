"""JWT de acceso, sesión actual (`GET /auth/me`) y la configuración que los gobierna.

Unidades: `app/auth/security.py` (create_access_token, decode_access_token,
expires_in_seconds), `app/auth/dependencies.py` (get_current_user),
`app/routes/auth.py` (read_current_user) y `app/core/config.py` (Settings).

La regresión que motivó AUTH-088 rompió la expiración de los tokens: los
tests T1, T3 y T4 fijan que un token vale exactamente
ACCESS_TOKEN_EXPIRE_MINUTES minutos. El instante exacto `exp == ahora` no se
prueba: python-jose usa su propio reloj y fijarlo exigiría parchear la
librería; la frontera se acota con ±5 s y +1 s.
"""

import base64
import json
import secrets
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from jose import jwt

from app.auth.dependencies import get_current_user
from app.auth.repository import AuthRepository
from app.auth.security import JWT_ALGORITHM, create_access_token, decode_access_token, expires_in_seconds
from app.auth.service import UserService
from app.core.config import MIN_JWT_SECRET_LENGTH, ConfigError, Settings
from app.core.errors import NotAuthenticatedError
from app.routes.auth import read_current_user

from .conftest import MakeUser

USER_ID = str(uuid4())


def _b64(data: dict[str, str]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def _now() -> datetime:
    return datetime.now(UTC)


# --- Emisión y expiración (T1–T4) ---


@pytest.mark.parametrize("minutes", [1, 30, 1440])
def test_token_expires_exactly_the_configured_minutes_after_issue(settings: Settings, minutes: int) -> None:
    # La regresión de AUTH-088: exp = iat + ACCESS_TOKEN_EXPIRE_MINUTES * 60 (D-AUTH-5).
    settings = replace(settings, access_token_expire_minutes=minutes)
    issued = datetime(2026, 10, 6, 9, 0, 30, 700_000, tzinfo=UTC)

    token = create_access_token(settings, USER_ID, now=issued)

    claims = jwt.get_unverified_claims(token)
    assert claims["iat"] == int(issued.timestamp())
    assert claims["exp"] == int(issued.timestamp()) + minutes * 60
    assert claims["sub"] == USER_ID
    assert jwt.get_unverified_header(token)["alg"] == "HS256"


@pytest.mark.parametrize("minutes", [1, 30, 1440])
def test_expires_in_matches_the_configured_minutes_in_seconds(settings: Settings, minutes: int) -> None:
    # `expires_in` de la respuesta del login sale de aquí: debe coincidir con el `exp` del token.
    assert expires_in_seconds(replace(settings, access_token_expire_minutes=minutes)) == minutes * 60


def test_fresh_token_decodes_to_its_subject(settings: Settings) -> None:
    assert decode_access_token(settings, create_access_token(settings, USER_ID)) == USER_ID


def _configured_lifetime(settings: Settings) -> int:
    # Desde la configuración, no desde expires_in_seconds: si esa función se rompe,
    # estos tests no deben validarse contra ella misma.
    assert settings.access_token_expire_minutes is not None
    return settings.access_token_expire_minutes * 60


def test_token_just_before_expiring_is_accepted(settings: Settings) -> None:
    issued = _now() - timedelta(seconds=_configured_lifetime(settings) - 5)
    assert decode_access_token(settings, create_access_token(settings, USER_ID, now=issued)) == USER_ID


def test_token_just_after_expiring_is_rejected(settings: Settings) -> None:
    issued = _now() - timedelta(seconds=_configured_lifetime(settings) + 1)
    assert decode_access_token(settings, create_access_token(settings, USER_ID, now=issued)) is None


def test_token_issued_days_ago_is_rejected(settings: Settings) -> None:
    issued = _now() - timedelta(days=3)
    assert decode_access_token(settings, create_access_token(settings, USER_ID, now=issued)) is None


# --- Firma, algoritmo y claims (T5–T7) ---


def _forged_tokens(settings: Settings) -> dict[str, str]:
    expires = _now() + timedelta(minutes=5)
    valid_payload = create_access_token(settings, USER_ID).split(".")[1]
    return {
        "otra clave": jwt.encode({"sub": USER_ID, "exp": expires}, secrets.token_urlsafe(48), algorithm="HS256"),
        "HS512 con la misma clave": jwt.encode({"sub": USER_ID, "exp": expires}, settings.jwt_secret_key, algorithm="HS512"),
        "alg none": f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{valid_payload}.",
    }


@pytest.mark.parametrize("case", ["otra clave", "HS512 con la misma clave", "alg none"])
def test_token_not_signed_with_hs256_and_our_key_is_rejected(settings: Settings, case: str) -> None:
    # D-AUTH-5: solo HS256 con JWT_SECRET_KEY.
    assert decode_access_token(settings, _forged_tokens(settings)[case]) is None


@pytest.mark.parametrize(
    ("sub", "with_exp"),
    [
        pytest.param(None, True, id="sin sub"),
        pytest.param("", True, id="sub vacío"),
        pytest.param(123, True, id="sub numérico"),
        pytest.param(USER_ID, False, id="sin exp"),
    ],
)
def test_token_without_a_usable_sub_or_exp_is_rejected(settings: Settings, sub: object, with_exp: bool) -> None:
    # D-AUTH-5: se exigen `sub` (un id no vacío) y `exp`; sin `exp` el token no caducaría nunca.
    claims: dict[str, object] = {} if sub is None else {"sub": sub}
    if with_exp:
        claims["exp"] = _now() + timedelta(minutes=5)
    token = jwt.encode(claims, settings.jwt_secret_key, algorithm=JWT_ALGORITHM)
    assert decode_access_token(settings, token) is None


def _malformed_tokens(settings: Settings) -> dict[str, str]:
    valid = create_access_token(settings, USER_ID)
    header, _, signature = valid.split(".")
    return {
        "vacío": "",
        "basura": "not-a-jwt",
        "dos segmentos": "abc.def",
        "truncado": valid[:-5],
        "payload manipulado": f"{header}.{_b64({'sub': str(uuid4())})}.{signature}",
    }


@pytest.mark.parametrize("case", ["vacío", "basura", "dos segmentos", "truncado", "payload manipulado"])
def test_malformed_token_is_rejected_without_raising(settings: Settings, case: str) -> None:
    # Cualquier fallo del token es "no autenticado" (None → 401), nunca una excepción (500).
    assert decode_access_token(settings, _malformed_tokens(settings)[case]) is None


# --- Usuario de la sesión: get_current_user y /auth/me (T8–T10) ---


def test_valid_token_resolves_to_its_active_user(settings: Settings, service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user()
    assert get_current_user(create_access_token(settings, str(user.id)), settings, service).id == user.id


def test_token_of_a_deleted_user_is_rejected(
    settings: Settings, service: UserService, auth_repo: AuthRepository, make_user: MakeUser
) -> None:
    # SPECS §19: borrar el usuario invalida sus tokens aunque no hayan caducado.
    user, _ = make_user()
    token = create_access_token(settings, str(user.id))
    assert auth_repo.delete_user(str(user.id))
    with pytest.raises(NotAuthenticatedError):
        get_current_user(token, settings, service)


def test_token_of_an_inactive_user_is_rejected(settings: Settings, service: UserService, make_user: MakeUser) -> None:
    # SPECS §17: un usuario inactivo no puede usar su token.
    user, _ = make_user(active=False)
    with pytest.raises(NotAuthenticatedError):
        get_current_user(create_access_token(settings, str(user.id)), settings, service)


@pytest.mark.parametrize("token", [None, ""])
def test_missing_token_is_not_authenticated(settings: Settings, service: UserService, token: str | None) -> None:
    # Sin token es 401 (no autenticado), nunca 403 (SPECS §21).
    with pytest.raises(NotAuthenticatedError):
        get_current_user(token, settings, service)


def test_current_user_view_has_profile_and_no_credentials(service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user(name="Ana")
    view = read_current_user(user, service)
    assert view.id == user.id
    assert view.profile is not None and view.profile.name == "Ana"
    assert "hashed_password" not in view.model_dump()


def test_current_user_view_tolerates_a_missing_profile(
    service: UserService, make_user: MakeUser, drop_profile: Callable[[str], None]
) -> None:
    # /auth/me no falla si el perfil no existe: lo devuelve como `null`.
    user, _ = make_user()
    drop_profile(str(user.id))
    assert read_current_user(user, service).profile is None


# --- Configuración del JWT (C1–C4 y el tope técnico de los minutos) ---


def _secret(length: int = 48) -> str:
    return "k" * length


def test_startup_requires_the_expiration_minutes() -> None:
    # D-AUTH-4: sin valor por defecto; la API no arranca sin ACCESS_TOKEN_EXPIRE_MINUTES.
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings(jwt_secret_key=_secret(), access_token_expire_minutes=None).require_auth()


def test_startup_requires_the_secret_key() -> None:
    with pytest.raises(ConfigError, match="JWT_SECRET_KEY"):
        Settings(access_token_expire_minutes=30).require_auth()


@pytest.mark.parametrize("minutes", [0, -1])
def test_non_positive_expiration_is_rejected_when_settings_are_built(minutes: int) -> None:
    # Se rechaza al construir Settings (__post_init__), antes incluso de require_auth().
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings(jwt_secret_key=_secret(), access_token_expire_minutes=minutes)


@pytest.mark.parametrize("value", ["abc", "1.5", "1e3"])
def test_non_integer_expiration_in_the_environment_is_rejected(value: str) -> None:
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings.from_env({"JWT_SECRET_KEY": _secret(), "ACCESS_TOKEN_EXPIRE_MINUTES": value})


def test_blank_expiration_in_the_environment_counts_as_missing() -> None:
    settings = Settings.from_env({"JWT_SECRET_KEY": _secret(), "ACCESS_TOKEN_EXPIRE_MINUTES": "   "})
    assert settings.access_token_expire_minutes is None
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        settings.require_auth()


def test_secret_key_needs_at_least_32_characters() -> None:
    # D-AUTH-4: HS256 necesita una clave de al menos 256 bits; se exige en caracteres.
    Settings(jwt_secret_key=_secret(MIN_JWT_SECRET_LENGTH), access_token_expire_minutes=30).require_auth()
    with pytest.raises(ConfigError, match="JWT_SECRET_KEY"):
        Settings(jwt_secret_key=_secret(MIN_JWT_SECRET_LENGTH - 1), access_token_expire_minutes=30).require_auth()


def test_secret_key_is_measured_after_trimming_spaces() -> None:
    padded = f"  {_secret(MIN_JWT_SECRET_LENGTH - 1)}  "
    settings = Settings.from_env({"JWT_SECRET_KEY": padded, "ACCESS_TOKEN_EXPIRE_MINUTES": "30"})
    with pytest.raises(ConfigError, match="JWT_SECRET_KEY"):
        settings.require_auth()


# Bug encontrado por esta batería (caso propuesto por la IA): 10**10 minutos pasaba
# Settings y después cada login daba 500 (OverflowError al firmar el token). Corregido
# con un tope TÉCNICO de 525600 minutos (1 año); la política de sesión la decide el CTO.


def test_expiration_at_the_technical_cap_is_accepted_and_signs_tokens(settings: Settings) -> None:
    at_cap = replace(settings, access_token_expire_minutes=525_600)
    at_cap.require_auth()
    assert decode_access_token(at_cap, create_access_token(at_cap, USER_ID)) == USER_ID


@pytest.mark.parametrize("minutes", [525_601, 10**10])
def test_expiration_beyond_the_technical_cap_is_rejected_at_startup(minutes: int) -> None:
    # El fallo debe aparecer al arrancar, no en cada login.
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings(jwt_secret_key=_secret(), access_token_expire_minutes=minutes)
    with pytest.raises(ConfigError, match="ACCESS_TOKEN_EXPIRE_MINUTES"):
        Settings.from_env({"JWT_SECRET_KEY": _secret(), "ACCESS_TOKEN_EXPIRE_MINUTES": str(minutes)})
