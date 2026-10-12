"""`POST /auth/login`: qué credenciales abren sesión y qué token se emite.

Unidades: la función de ruta `login` (`app/routes/auth.py`), llamada
directamente con un `OAuth2PasswordRequestForm` construido a mano;
`UserService.authenticate` y `verify_password`. Sin HTTP.

`burn_password_check` (verificación contra un hash ficticio) iguala el tiempo
de respuesta cuando el email no existe o es inválido, para no revelar qué
emails están registrados (SPECS §19). Los tests lo espían con monkeypatch.
"""

from collections.abc import Callable

import pytest
from fastapi.security import OAuth2PasswordRequestForm

import app.auth.security as security
import app.auth.service as service_module
import app.routes.auth as auth_routes
from app.auth.models import Token
from app.auth.security import decode_access_token
from app.auth.service import UserService
from app.core.config import Settings
from app.core.errors import InvalidCredentialsError

from .conftest import MakeUser


def _login(settings: Settings, service: UserService, email: str, password: str) -> Token:
    return auth_routes.login(OAuth2PasswordRequestForm(username=email, password=password), settings, service)


@pytest.fixture
def burn_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Espía de `burn_password_check` en la ruta y en el servicio: anota cada llamada."""
    calls: list[str] = []

    def spy(password: str) -> None:
        calls.append(password)

    monkeypatch.setattr(auth_routes, "burn_password_check", spy)
    monkeypatch.setattr(service_module, "burn_password_check", spy)
    return calls


@pytest.fixture
def bcrypt_verify_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Espía de la comparación bcrypt real: anota cada contraseña comparada y delega en la original."""
    calls: list[str] = []
    original: Callable[[str, str], bool] = security.bcrypt.verify

    def spy(password: str, hashed: str) -> bool:
        calls.append(password)
        return original(password, hashed)

    monkeypatch.setattr(security.bcrypt, "verify", spy)
    return calls


# --- Camino feliz (L1) y límite (L2) ---


def test_valid_credentials_issue_a_token_for_that_user(settings: Settings, service: UserService, make_user: MakeUser) -> None:
    user, password = make_user()

    token = _login(settings, service, user.email, password)

    assert decode_access_token(settings, token.access_token) == str(user.id)
    assert token.token_type == "bearer"
    # `expires_in` dice al cliente lo mismo que el `exp` del token (la regresión de AUTH-088).
    assert token.expires_in == settings.access_token_expire_minutes * 60  # type: ignore[operator]


def test_email_with_capitals_and_spaces_still_logs_in(settings: Settings, service: UserService, make_user: MakeUser) -> None:
    # D-AUTH-6: el email se normaliza (recortado y en minúsculas) también en el login.
    user, password = make_user("ana.lopez@example.invalid")
    token = _login(settings, service, "  Ana.Lopez@EXAMPLE.invalid ", password)
    assert decode_access_token(settings, token.access_token) == str(user.id)


# --- Modos de fallo (L3–L7) ---


def test_wrong_password_and_unknown_email_fail_the_same_way(
    settings: Settings, service: UserService, make_user: MakeUser, burn_calls: list[str]
) -> None:
    # Sin enumeración de usuarios: el mismo error exista o no el email.
    user, password = make_user()
    with pytest.raises(InvalidCredentialsError) as wrong_password:
        _login(settings, service, user.email, password + "x")
    assert burn_calls == []  # el email existe: se compara con su hash real

    with pytest.raises(InvalidCredentialsError) as unknown_email:
        _login(settings, service, "nobody@example.invalid", password)
    # El email no existe: se verifica igualmente contra un hash ficticio.
    assert burn_calls == [password]

    assert (wrong_password.value.code, wrong_password.value.detail) == (unknown_email.value.code, unknown_email.value.detail)


@pytest.mark.parametrize("email", ["not-an-email", "", "a@b", "a b@example.invalid"])
def test_malformed_email_is_rejected_as_bad_credentials_after_burning(
    settings: Settings, service: UserService, burn_calls: list[str], email: str
) -> None:
    # Un email mal formado da el mismo 401 que unas credenciales incorrectas (no un 422),
    # y también paga el coste de bcrypt.
    with pytest.raises(InvalidCredentialsError):
        _login(settings, service, email, "irrelevant-password")
    assert burn_calls == ["irrelevant-password"]


def test_password_over_72_bytes_never_reaches_bcrypt(
    service: UserService, make_user: MakeUser, bcrypt_verify_calls: list[str]
) -> None:
    # D-AUTH-7: una contraseña de más de 72 bytes nunca pudo registrarse; no se compara
    # (bcrypt la truncaría y podría coincidir con la real).
    user, password = make_user()
    too_long = (password * 10)[:73]
    assert len(too_long.encode("utf-8")) == 73

    assert service.authenticate(user.email, too_long) is None
    assert security.verify_password(too_long, user.hashed_password) is False
    assert bcrypt_verify_calls == []
    # Control del espía: una contraseña válida sí llega a bcrypt.
    assert service.authenticate(user.email, password) is not None
    assert bcrypt_verify_calls == [password]


def test_password_with_nul_byte_fails_like_bad_credentials_without_reaching_bcrypt(
    settings: Settings, service: UserService, make_user: MakeUser, bcrypt_verify_calls: list[str]
) -> None:
    # Bug encontrado por esta batería: bcrypt lanza una excepción con un NUL y el login
    # daba 500. Ninguna contraseña registrada puede contenerlo: es un 401 normal, igual
    # exista o no el email (el burn tampoco llega a bcrypt, como con más de 72 bytes).
    user, password = make_user()
    with_nul = f"{password[:4]}\x00{password[4:]}"

    with pytest.raises(InvalidCredentialsError) as known_email:
        _login(settings, service, user.email, with_nul)
    with pytest.raises(InvalidCredentialsError) as unknown_email:
        _login(settings, service, "nobody@example.invalid", with_nul)

    assert (known_email.value.code, known_email.value.detail) == (unknown_email.value.code, unknown_email.value.detail)
    assert bcrypt_verify_calls == []
    # Control del espía: una contraseña válida sí llega a bcrypt.
    assert service.authenticate(user.email, password) is not None
    assert bcrypt_verify_calls == [password]


def test_inactive_user_cannot_log_in_even_with_the_right_password(
    settings: Settings, service: UserService, make_user: MakeUser
) -> None:
    # SPECS §17: `is_active = false` bloquea el login.
    user, password = make_user(active=False)
    assert service.authenticate(user.email, password) is None
    with pytest.raises(InvalidCredentialsError):
        _login(settings, service, user.email, password)


def test_empty_password_never_authenticates(settings: Settings, service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user()
    assert service.authenticate(user.email, "") is None
    with pytest.raises(InvalidCredentialsError):
        _login(settings, service, user.email, "")
