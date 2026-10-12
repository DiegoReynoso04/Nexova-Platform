"""`POST /auth/reset-password`: qué enlace cambia la contraseña y cuál no.

Unidades: la función de ruta `reset_password` (`app/routes/auth.py`),
`UserService.reset_password` y `AuthRepository.consume_reset_token`. Sin HTTP.

Decisiones (docs/auth-password-reset.md, SPECS Parte D): el enlace vale una
sola vez y hasta `expires_at` (excluido); cualquier enlace inválido da el
mismo 400, pero la auditoría guarda el motivo real; validar, cambiar la
contraseña y marcar el enlace como usado es una única operación bajo lock.
"""

import secrets
import sys
import threading
from collections.abc import Callable
from uuid import uuid4

import pytest
from pydantic import ValidationError
from tinydb import TinyDB

from app.auth.models import MAX_SECRET_INPUT_LENGTH, AuditEvent, ResetPasswordRequest, UserInDB
from app.auth.repository import AUDIT_TABLE, RESET_TOKENS_TABLE, AuthRepository, ResetTokenStatus
from app.auth.security import hash_reset_token
from app.auth.service import UserService
from app.core.errors import InvalidResetTokenError
from app.core.storage import GuardedJSONStorage, Store
from app.routes.auth import PASSWORD_UPDATED_DETAIL, reset_password

from .conftest import CLIENT_IP, FakeClock, MakeUser, ReadTable, fake_request

MINUTES = 30


def _link(service: UserService, user: UserInDB) -> str:
    pending = service.request_password_reset(user.email, MINUTES, CLIENT_IP)
    assert pending is not None
    return pending.token


def _reset(service: UserService, token: str, new_password: str) -> str:
    return reset_password(ResetPasswordRequest(token=token, new_password=new_password), fake_request(), service).detail


def _last_audit(read_table: ReadTable) -> tuple[str, str | None, str | None]:
    row = read_table(AUDIT_TABLE)[-1]
    return row["event"], row["user_id"], row["reason"]


# --- Camino feliz (RP1) ---


def test_valid_link_sets_the_new_password_and_is_marked_used(
    service: UserService, clock: FakeClock, read_table: ReadTable, make_user: MakeUser
) -> None:
    user, old_password = make_user()
    token = _link(service, user)
    new_password = secrets.token_urlsafe(12)

    assert _reset(service, token, new_password) == PASSWORD_UPDATED_DETAIL

    assert service.authenticate(user.email, new_password) is not None
    assert service.authenticate(user.email, old_password) is None
    [row] = read_table(RESET_TOKENS_TABLE)
    assert row["used_at"] == clock.now.isoformat()
    assert _last_audit(read_table) == (AuditEvent.RESET_COMPLETED, str(user.id), None)


# --- Límites (RP2) ---


def test_link_works_one_second_before_expiring(
    service: UserService, auth_repo: AuthRepository, clock: FakeClock, make_user: MakeUser, known_password: tuple[str, str]
) -> None:
    user, _ = make_user()
    token = _link(service, user)
    clock.advance(minutes=MINUTES, seconds=-1)
    assert auth_repo.consume_reset_token(hash_reset_token(token), known_password[1])[0] == ResetTokenStatus.VALID


def test_link_is_expired_exactly_at_its_expiry_instant(
    service: UserService, auth_repo: AuthRepository, clock: FakeClock, make_user: MakeUser, known_password: tuple[str, str]
) -> None:
    # `expires_at` ya no es válido: un enlace de 30 minutos dura 30 minutos, no 30 y un instante.
    user, _ = make_user()
    token = _link(service, user)
    clock.advance(minutes=MINUTES)
    assert auth_repo.consume_reset_token(hash_reset_token(token), known_password[1])[0] == ResetTokenStatus.EXPIRED


def test_successful_reset_voids_every_other_pending_link_of_the_user(
    service: UserService, auth_repo: AuthRepository, read_table: ReadTable, make_user: MakeUser
) -> None:
    # Hoy solo queda un pendiente por usuario (replace_reset_token), así que el
    # segundo se fabrica a mano: la purga en el reset es defensa en profundidad.
    user, _ = make_user()
    used, spare = _link(service, user), secrets.token_urlsafe(32)
    pending = read_table(RESET_TOKENS_TABLE)[0]
    with TinyDB(auth_repo.path, storage=GuardedJSONStorage, store=Store.AUTH, encoding="utf-8") as db:
        db.table(RESET_TOKENS_TABLE).insert({**pending, "id": str(uuid4()), "token_hash": hash_reset_token(spare)})

    _reset(service, used, secrets.token_urlsafe(12))

    assert [row["token_hash"] for row in read_table(RESET_TOKENS_TABLE)] == [hash_reset_token(used)]
    with pytest.raises(InvalidResetTokenError):
        _reset(service, spare, secrets.token_urlsafe(12))


# --- Modos de fallo (RP3) ---


def _used(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    _reset(service, token, secrets.token_urlsafe(12))


def _expired(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    clock.advance(minutes=MINUTES + 1)


def _new_link(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    _link(service, user)


def _changed(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    service.change_password(user, password, secrets.token_urlsafe(12), CLIENT_IP)


def _deleted(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    assert repo.delete_user(str(user.id))


def _deactivated(service: UserService, repo: AuthRepository, clock: FakeClock, user: UserInDB, password: str, token: str) -> None:
    assert repo.update_user(str(user.id), {"is_active": False}) is not None


@pytest.mark.parametrize(
    ("sabotage", "reason", "row_survives"),
    [
        pytest.param(_used, "used", True, id="ya usado"),
        pytest.param(_expired, "expired", True, id="caducado"),
        # Anulado: la fila desaparece, así que la auditoría ya no sabe de quién era.
        pytest.param(_new_link, "unknown", False, id="anulado por un enlace nuevo"),
        pytest.param(_changed, "unknown", False, id="anulado por change-password"),
        pytest.param(_deleted, "unknown", True, id="usuario borrado"),
        pytest.param(_deactivated, "unknown", True, id="usuario inactivo"),
    ],
)
def test_unusable_link_is_rejected_and_audited_with_the_real_reason(
    service: UserService,
    auth_repo: AuthRepository,
    clock: FakeClock,
    read_table: ReadTable,
    make_user: MakeUser,
    sabotage: Callable[..., None],
    reason: str,
    row_survives: bool,
) -> None:
    # El cliente recibe siempre el mismo 400; la auditoría distingue el motivo.
    user, password = make_user()
    token = _link(service, user)
    sabotage(service, auth_repo, clock, user, password, token)
    before = auth_repo.get_user(str(user.id))

    with pytest.raises(InvalidResetTokenError):
        _reset(service, token, secrets.token_urlsafe(12))

    # La contraseña no cambia (ni se resucita un usuario borrado).
    assert auth_repo.get_user(str(user.id)) == before
    assert _last_audit(read_table) == (AuditEvent.RESET_REJECTED, str(user.id) if row_survives else None, reason)


def test_unknown_link_is_rejected_without_a_user_in_the_audit(service: UserService, read_table: ReadTable) -> None:
    with pytest.raises(InvalidResetTokenError):
        _reset(service, secrets.token_urlsafe(32), secrets.token_urlsafe(12))
    assert _last_audit(read_table) == (AuditEvent.RESET_REJECTED, None, "unknown")


@pytest.mark.parametrize(
    "token",
    [pytest.param("", id="vacío"), pytest.param("t" * (MAX_SECRET_INPUT_LENGTH + 1), id="513 caracteres")],
)
def test_empty_or_oversized_token_is_rejected_before_any_lookup(token: str) -> None:
    # 512 es un tope generoso contra cuerpos desmesurados; la validez real la decide la base.
    ResetPasswordRequest(token="t" * MAX_SECRET_INPUT_LENGTH, new_password=secrets.token_urlsafe(12))
    with pytest.raises(ValidationError) as exc:
        ResetPasswordRequest(token=token, new_password=secrets.token_urlsafe(12))
    assert [error["loc"] for error in exc.value.errors()] == [("token",)]


# --- Concurrencia (caso propuesto por la IA) ---

RACE_ROUNDS = 25


def test_two_simultaneous_resets_with_the_same_link_succeed_exactly_once(
    service: UserService, auth_repo: AuthRepository, make_user: MakeUser, known_password: tuple[str, str]
) -> None:
    # Validar y marcar como usado ocurre bajo el lock del repositorio: aunque dos
    # peticiones lleguen a la vez, solo una cambia la contraseña. La barrera hace
    # que ambas empiecen juntas y un intervalo de cambio de hilo mínimo, que se
    # intercalen todo lo posible (sin sleeps). Con el lock el resultado es siempre
    # el mismo. Sin él (medido en 200 rondas) ninguna ronda sale bien: unas dan dos
    # VALID y la mayoría deja el archivo corrupto (503); el error se anota en vez de
    # perderse en el hilo, para que el fallo diga cuál de las dos pasó.
    user, _ = make_user()
    previous_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for _ in range(RACE_ROUNDS):
            token_hash = hash_reset_token(_link(service, user))
            barrier = threading.Barrier(2)
            results: list[str] = []

            def consume() -> None:
                barrier.wait()
                try:
                    results.append(auth_repo.consume_reset_token(token_hash, known_password[1])[0].value)
                except Exception as exc:  # noqa: BLE001 — se anota para el mensaje del assert
                    results.append(type(exc).__name__)

            # `daemon`: si un hilo se queda bloqueado, no impide que termine el proceso de pytest.
            threads = [threading.Thread(target=consume, daemon=True) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
                # Un deadlock futuro debe fallar, no colgar la suite.
                assert not thread.is_alive(), "posible bloqueo en consume_reset_token"

            assert sorted(results) == [ResetTokenStatus.USED, ResetTokenStatus.VALID]
    finally:
        sys.setswitchinterval(previous_interval)
