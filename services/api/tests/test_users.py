"""`/users` (listar, leer, actualizar y borrar): quién puede hacer qué sobre qué usuario.

Unidades: las funciones de ruta de `app/routes/users.py` (`list_users`,
`get_user`, `update_user`, `delete_user`), llamadas con el usuario autenticado
ya resuelto; `require_admin` y `ensure_self_or_admin` (`dependencies.py`) y
`UserService`. Sin HTTP.

Reglas (SPECS §21, D-AUTH-13 y H-1/D-PWD-12): cada uno se gestiona a sí mismo
y un admin gestiona a todos; solo un admin cambia `role` o `password` (los
demás usan `POST /auth/change-password`, que exige la contraseña actual).
"""

import secrets
from uuid import uuid4

import pytest

from app.auth.dependencies import get_current_user, require_admin
from app.auth.models import UserInDB, UserRole, UserUpdate
from app.auth.repository import AuthRepository
from app.auth.security import create_access_token, verify_password
from app.auth.service import UserService
from app.core.config import Settings
from app.core.errors import EmailAlreadyRegisteredError, ForbiddenError, NotAuthenticatedError, UserNotFoundError
from app.routes import users as routes

from .conftest import MakeUser

NON_ADMIN_ROLES = [pytest.param(UserRole.USER, id="user"), pytest.param(UserRole.MANAGER, id="manager")]


def _stored(auth_repo: AuthRepository, user: UserInDB) -> UserInDB:
    stored = auth_repo.get_user(str(user.id))
    assert stored is not None
    return stored


# --- Listado y permiso de admin (U1, U2) ---


def test_admin_lists_every_user_without_credentials(service: UserService, make_user: MakeUser) -> None:
    admin, _ = make_user(role=UserRole.ADMIN)
    user, _ = make_user()

    listed = routes.list_users(require_admin(admin), service)

    assert {item.id for item in listed} == {admin.id, user.id}
    assert all("hashed_password" not in item.model_dump() for item in listed)


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_is_forbidden_from_admin_only_routes(make_user: MakeUser, role: UserRole) -> None:
    # Autenticado pero sin permiso: 403, no 401 (SPECS §21). `manager` no es admin.
    user, _ = make_user(role=role)
    with pytest.raises(ForbiddenError) as exc:
        require_admin(user)
    assert exc.value.status_code == 403


# --- Leer un usuario (U3) ---


def test_user_reads_itself_and_admin_reads_anyone(service: UserService, make_user: MakeUser) -> None:
    admin, _ = make_user(role=UserRole.ADMIN)
    user, _ = make_user()

    assert routes.get_user(user.id, user, service).id == user.id
    assert routes.get_user(user.id, admin, service).id == user.id


def test_admin_reading_a_missing_user_gets_not_found(service: UserService, make_user: MakeUser) -> None:
    admin, _ = make_user(role=UserRole.ADMIN)
    with pytest.raises(UserNotFoundError):
        routes.get_user(uuid4(), admin, service)


@pytest.mark.parametrize("target_exists", [pytest.param(True, id="existe"), pytest.param(False, id="no existe")])
def test_non_admin_reading_another_user_is_forbidden_whether_it_exists_or_not(
    service: UserService, make_user: MakeUser, target_exists: bool
) -> None:
    # El 403 llega antes de buscar: un no-admin no puede averiguar qué ids existen.
    user, _ = make_user()
    target = make_user()[0].id if target_exists else uuid4()
    with pytest.raises(ForbiddenError):
        routes.get_user(target, user, service)


# --- Actualizar: email (U4, U5, U8) ---


def test_user_changes_its_own_email_and_it_is_stored_normalized(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser
) -> None:
    user, _ = make_user()

    updated = routes.update_user(user.id, UserUpdate(email="  Nueva.Direccion@EXAMPLE.invalid "), user, service)

    assert updated.email == "nueva.direccion@example.invalid"
    assert _stored(auth_repo, user).email == "nueva.direccion@example.invalid"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="cuerpo vacío"),
        pytest.param({"password": None}, id="password null"),
        pytest.param({"role": None}, id="role null"),
    ],
)
def test_update_without_values_changes_nothing_and_is_not_forbidden(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, payload: dict[str, None]
) -> None:
    # D-AUTH-13: semántica parcial; `null` cuenta como «no enviado», así que un no-admin
    # que manda `password: null` no choca con la regla de H-1.
    user, _ = make_user()
    before = _stored(auth_repo, user)

    assert routes.update_user(user.id, UserUpdate.model_validate(payload), user, service).id == user.id
    assert _stored(auth_repo, user) == before


def test_resending_your_own_email_is_not_a_duplicate(service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user("ana@example.invalid")
    assert routes.update_user(user.id, UserUpdate(email="ANA@example.invalid"), user, service).email == user.email


@pytest.mark.parametrize("email", ["luis@example.invalid", "  LUIS@Example.INVALID "])
def test_taking_another_users_email_is_rejected(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, email: str
) -> None:
    # La unicidad se comprueba sobre el email normalizado.
    user, _ = make_user("ana@example.invalid")
    make_user("luis@example.invalid")

    with pytest.raises(EmailAlreadyRegisteredError):
        routes.update_user(user.id, UserUpdate(email=email), user, service)
    assert _stored(auth_repo, user).email == "ana@example.invalid"


# --- Actualizar: contraseña y rol (U6, U7, U9) ---


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_cannot_set_a_password_and_nothing_in_the_request_is_applied(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, role: UserRole
) -> None:
    # H-1: fijar la contraseña aquí esquivaría la contraseña actual que exige
    # /auth/change-password. Tampoco se aplica el email que venía en la misma petición.
    user, _ = make_user(role=role)
    before = _stored(auth_repo, user)
    payload = UserUpdate(email="otro@example.invalid", password=secrets.token_urlsafe(12))

    with pytest.raises(ForbiddenError, match="change-password"):
        routes.update_user(user.id, payload, user, service)
    assert _stored(auth_repo, user) == before


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_non_admin_cannot_change_roles_not_even_its_own(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, role: UserRole
) -> None:
    user, _ = make_user(role=role)
    with pytest.raises(ForbiddenError, match="only an admin can change roles"):
        routes.update_user(user.id, UserUpdate(role=UserRole.ADMIN), user, service)
    assert _stored(auth_repo, user).role == role


def test_role_rule_is_checked_before_the_password_rule(service: UserService, make_user: MakeUser) -> None:
    # Con `role` y `password` a la vez, el error explica el intento de escalar privilegios,
    # no el de la contraseña.
    user, _ = make_user()
    payload = UserUpdate(role=UserRole.ADMIN, password=secrets.token_urlsafe(12))
    with pytest.raises(ForbiddenError, match="only an admin can change roles"):
        routes.update_user(user.id, payload, user, service)


def test_admin_sets_another_users_password_and_role(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser
) -> None:
    # Capacidad de AUTH-01 que conserva el admin (riesgo residual documentado en SPECS §27).
    admin, _ = make_user(role=UserRole.ADMIN)
    user, old_password = make_user()
    new_password = secrets.token_urlsafe(12)

    updated = routes.update_user(user.id, UserUpdate(password=new_password, role=UserRole.MANAGER), admin, service)

    assert updated.role == UserRole.MANAGER
    stored = _stored(auth_repo, user)
    assert verify_password(new_password, stored.hashed_password)
    assert not verify_password(old_password, stored.hashed_password)


@pytest.mark.parametrize(
    "payload",
    [pytest.param({}, id="cuerpo vacío"), pytest.param({"email": "nadie@example.invalid"}, id="con email")],
)
def test_admin_updating_a_missing_user_gets_not_found(
    service: UserService, make_user: MakeUser, payload: dict[str, str]
) -> None:
    # Como en GET: el admin sí recibe 404, y la actualización no crea al usuario.
    admin, _ = make_user(role=UserRole.ADMIN)
    with pytest.raises(UserNotFoundError):
        routes.update_user(uuid4(), UserUpdate.model_validate(payload), admin, service)
    assert service.get_user_by_email("nadie@example.invalid") is None


# --- Borrar (U10, U11) ---


def test_deleting_yourself_removes_profile_and_invalidates_your_token(
    settings: Settings, service: UserService, auth_repo: AuthRepository, make_user: MakeUser
) -> None:
    user, _ = make_user(name="Ana")
    token = create_access_token(settings, str(user.id))

    routes.delete_user(user.id, user, service)

    assert auth_repo.get_user(str(user.id)) is None
    # Nunca queda un perfil huérfano.
    assert auth_repo.get_profile(str(user.id)) is None
    # El token sigue sin caducar, pero ya no autentica a nadie.
    with pytest.raises(NotAuthenticatedError):
        get_current_user(token, settings, service)


def test_non_admin_cannot_delete_another_user(service: UserService, auth_repo: AuthRepository, make_user: MakeUser) -> None:
    user, _ = make_user()
    other, _ = make_user()
    with pytest.raises(ForbiddenError):
        routes.delete_user(other.id, user, service)
    assert auth_repo.get_user(str(other.id)) is not None


def test_deleting_a_missing_or_already_deleted_user_is_not_found(service: UserService, make_user: MakeUser) -> None:
    admin, _ = make_user(role=UserRole.ADMIN)
    user, _ = make_user()

    with pytest.raises(UserNotFoundError):
        routes.delete_user(uuid4(), admin, service)

    routes.delete_user(user.id, admin, service)
    with pytest.raises(UserNotFoundError):
        routes.delete_user(user.id, admin, service)
