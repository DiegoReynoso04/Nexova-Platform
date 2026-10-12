"""`POST /auth/change-password`: cambiar la contraseña con sesión, demostrando la actual.

Unidades: la función de ruta `change_password` (`app/routes/auth.py`),
`UserService.change_password` y `AuthRepository.update_password`. Sin HTTP.

Decisiones (docs/auth-password-reset.md, SPECS Parte D): se exige la
contraseña actual (es la vía de H-1 para los no-admin); si no coincide es un
400, no un 401, porque la sesión sigue siendo válida; cambiar la contraseña
anula los enlaces de restablecimiento pendientes; cada intento se audita.
"""

import secrets

import pytest

from app.auth.models import AuditEvent, ChangePasswordRequest, UserInDB
from app.auth.repository import AUDIT_TABLE, RESET_TOKENS_TABLE, AuthRepository
from app.auth.service import UserService
from app.core.config import Settings
from app.core.errors import IncorrectPasswordError, UserNotFoundError
from app.routes.auth import PASSWORD_UPDATED_DETAIL, change_password

from .conftest import CLIENT_IP, MakeUser, ReadTable, fake_request


def _change(service: UserService, user: UserInDB, current: str, new: str) -> str:
    payload = ChangePasswordRequest(current_password=current, new_password=new)
    return change_password(payload, fake_request(), user, service).detail


def _audits(read_table: ReadTable) -> list[tuple[str, str | None, str | None]]:
    return [(row["event"], row["user_id"], row["ip"]) for row in read_table(AUDIT_TABLE)]


# --- Camino feliz (CP1) ---


def test_change_sets_the_new_password_audits_it_and_voids_pending_reset_links(
    settings: Settings, service: UserService, read_table: ReadTable, make_user: MakeUser
) -> None:
    user, old_password = make_user()
    assert service.request_password_reset(user.email, settings.password_reset_token_minutes, CLIENT_IP) is not None
    new_password = secrets.token_urlsafe(12)

    assert _change(service, user, old_password, new_password) == PASSWORD_UPDATED_DETAIL

    assert service.authenticate(user.email, new_password) is not None
    assert service.authenticate(user.email, old_password) is None
    # Quien cambia la contraseña porque sospecha de un enlace robado lo deja sin valor.
    assert read_table(RESET_TOKENS_TABLE) == []
    assert _audits(read_table)[-1] == (AuditEvent.PASSWORD_CHANGED, str(user.id), CLIENT_IP)


# --- Límites (CP2) ---


def test_new_password_equal_to_the_current_one_is_accepted(
    service: UserService, read_table: ReadTable, make_user: MakeUser
) -> None:
    # D-PWD-10: no se exige que sea distinta de la actual.
    user, password = make_user()
    assert _change(service, user, password, password) == PASSWORD_UPDATED_DETAIL
    assert service.authenticate(user.email, password) is not None
    assert _audits(read_table)[-1][0] == AuditEvent.PASSWORD_CHANGED


def test_current_password_over_72_bytes_is_simply_incorrect(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, bcrypt_verify_calls: list[str]
) -> None:
    # La actual admite hasta 512 caracteres (no se valida como contraseña nueva), pero
    # una de más de 72 bytes nunca pudo registrarse: es incorrecta sin llegar a bcrypt.
    user, password = make_user()
    too_long = (password * 10)[:73]

    with pytest.raises(IncorrectPasswordError):
        _change(service, user, too_long, secrets.token_urlsafe(12))
    assert bcrypt_verify_calls == []
    assert auth_repo.get_user(str(user.id)) == user


# --- Modos de fallo (CP3) ---


def test_wrong_current_password_is_a_400_that_changes_nothing_and_is_audited(
    service: UserService, auth_repo: AuthRepository, read_table: ReadTable, make_user: MakeUser
) -> None:
    # 400 y no 401: la sesión es válida; un 401 haría que el frontend cerrara la sesión.
    user, password = make_user()

    with pytest.raises(IncorrectPasswordError) as exc:
        _change(service, user, password + "x", secrets.token_urlsafe(12))

    assert exc.value.status_code == 400
    assert auth_repo.get_user(str(user.id)) == user
    assert _audits(read_table) == [(AuditEvent.PASSWORD_CHANGE_REJECTED, str(user.id), CLIENT_IP)]


def test_current_password_with_nul_byte_is_incorrect_without_reaching_bcrypt(
    service: UserService, auth_repo: AuthRepository, read_table: ReadTable, make_user: MakeUser, bcrypt_verify_calls: list[str]
) -> None:
    # Cierra el caso del fix 988ff96: antes era un 500 (bcrypt lanza con un NUL). La
    # contraseña actual no se valida como nueva, así que lo resuelve verify_password.
    user, password = make_user()

    with pytest.raises(IncorrectPasswordError):
        _change(service, user, f"{password[:4]}\x00{password[4:]}", secrets.token_urlsafe(12))

    assert bcrypt_verify_calls == []
    assert auth_repo.get_user(str(user.id)) == user
    assert _audits(read_table) == [(AuditEvent.PASSWORD_CHANGE_REJECTED, str(user.id), CLIENT_IP)]


def test_user_deleted_after_authenticating_gets_not_found(
    service: UserService, auth_repo: AuthRepository, read_table: ReadTable, make_user: MakeUser
) -> None:
    # Carrera: el token se resolvió y el usuario se borró antes del cambio. No se
    # recrea el usuario ni se audita un cambio que no ocurrió.
    user, password = make_user()
    assert auth_repo.delete_user(str(user.id))

    with pytest.raises(UserNotFoundError):
        _change(service, user, password, secrets.token_urlsafe(12))

    assert auth_repo.get_user(str(user.id)) is None
    assert _audits(read_table) == []
