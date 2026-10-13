"""`POST /auth/forgot-password`: cuándo se crea un enlace, qué se guarda y qué se envía.

Unidades: la función de ruta `forgot_password` y la tarea `send_reset_email`
(`app/routes/auth.py`), `UserService.request_password_reset` y
`AuthRepository.replace_reset_token`. Sin HTTP: la ruta se llama con un
`BackgroundTasks` real y se inspeccionan las tareas encoladas en vez de
ejecutarlas tras la respuesta.

Decisiones (docs/auth-password-reset.md, SPECS Parte D): la respuesta es la
misma exista o no el email (sin enumeración); en la base solo se guarda el
SHA-256 del token; solo vale el último enlace pedido; un fallo del proveedor
de email nunca cambia la respuesta y solo se registra el tipo de error.
"""

from datetime import datetime, timedelta

import pytest
from fastapi import BackgroundTasks

from app.auth.email import DisabledEmailSender, EmailDeliveryError, EmailSender
from app.auth.models import AuditEvent, ForgotPasswordRequest
from app.auth.repository import AUDIT_TABLE, RESET_TOKENS_TABLE, AuthRepository, ResetTokenStatus
from app.auth.security import hash_reset_token
from app.auth.service import PendingResetEmail, UserService
from app.core.config import Settings
from app.routes.auth import FORGOT_PASSWORD_DETAIL, forgot_password, send_reset_email

from .conftest import CLIENT_IP, FakeClock, FakeEmailSender, MakeUser, ReadTable, fake_request
from .support import capture_logs


def _forgot(
    settings: Settings, service: UserService, sender: FakeEmailSender, email: str
) -> tuple[str, BackgroundTasks]:
    tasks = BackgroundTasks()
    response = forgot_password(ForgotPasswordRequest(email=email), fake_request(), tasks, settings, service, sender)
    return response.detail, tasks


# --- Camino feliz (FP1) ---


def test_registered_email_gets_a_hashed_token_an_audit_row_and_a_queued_email(
    settings: Settings,
    service: UserService,
    auth_repo: AuthRepository,
    fake_sender: FakeEmailSender,
    clock: FakeClock,
    read_table: ReadTable,
    make_user: MakeUser,
) -> None:
    user, _ = make_user()

    detail, tasks = _forgot(settings, service, fake_sender, user.email)

    assert detail == FORGOT_PASSWORD_DETAIL
    assert [task.func for task in tasks.tasks] == [send_reset_email]
    pending = tasks.tasks[0].args[2]
    assert isinstance(pending, PendingResetEmail) and pending.email == user.email

    # Solo el SHA-256 llega a la base: el token en claro no aparece en el archivo.
    [row] = read_table(RESET_TOKENS_TABLE)
    assert row["user_id"] == str(user.id)
    assert row["token_hash"] == hash_reset_token(pending.token)
    assert pending.token not in auth_repo.path.read_text(encoding="utf-8")
    assert datetime.fromisoformat(row["expires_at"]) == clock.now + timedelta(minutes=settings.password_reset_token_minutes)
    assert row["used_at"] is None

    [audit] = read_table(AUDIT_TABLE)
    assert (audit["event"], audit["user_id"], audit["ip"], audit["reason"]) == (
        AuditEvent.RESET_REQUESTED,
        str(user.id),
        CLIENT_IP,
        None,
    )

    # La tarea encolada envía el enlace con ese mismo token al email del usuario.
    tasks.tasks[0].func(*tasks.tasks[0].args)
    [message] = fake_sender.messages
    assert message.to == user.email and f"token={pending.token}" in message.text


# --- Modos de fallo: email desconocido o usuario inactivo (FP2) ---


@pytest.mark.parametrize("case", ["desconocido", "inactivo"])
def test_unknown_or_inactive_email_gets_the_same_answer_and_nothing_else(
    settings: Settings,
    service: UserService,
    fake_sender: FakeEmailSender,
    read_table: ReadTable,
    make_user: MakeUser,
    case: str,
) -> None:
    # Sin enumeración: la misma respuesta, pero sin token, sin email y sin `user_id`
    # en la auditoría (tampoco el del usuario inactivo).
    email = "nobody@example.invalid" if case == "desconocido" else make_user(active=False)[0].email

    assert service.request_password_reset(email, settings.password_reset_token_minutes, CLIENT_IP) is None
    detail, tasks = _forgot(settings, service, fake_sender, email)

    assert detail == FORGOT_PASSWORD_DETAIL
    assert tasks.tasks == []
    assert read_table(RESET_TOKENS_TABLE) == []
    audits = read_table(AUDIT_TABLE)
    assert {(row["event"], row["user_id"], row["reason"]) for row in audits} == {
        (AuditEvent.RESET_REQUESTED, None, "unknown_email")
    }


# --- Límites (FP3) ---


def test_email_is_normalized_before_looking_up_the_user(
    settings: Settings, service: UserService, fake_sender: FakeEmailSender, make_user: MakeUser
) -> None:
    user, _ = make_user("ana.lopez@example.invalid")
    _, tasks = _forgot(settings, service, fake_sender, "  Ana.Lopez@EXAMPLE.invalid ")
    assert tasks.tasks[0].args[2].email == user.email


def test_only_the_latest_link_is_pending_after_two_requests(
    settings: Settings,
    service: UserService,
    auth_repo: AuthRepository,
    read_table: ReadTable,
    make_user: MakeUser,
    known_password: tuple[str, str],
) -> None:
    user, _ = make_user()
    minutes = settings.password_reset_token_minutes
    first = service.request_password_reset(user.email, minutes, CLIENT_IP)
    second = service.request_password_reset(user.email, minutes, CLIENT_IP)
    assert first is not None and second is not None

    assert [row["token_hash"] for row in read_table(RESET_TOKENS_TABLE)] == [hash_reset_token(second.token)]
    # El primer enlace ya no existe: usarlo es un token desconocido.
    status, _ = auth_repo.consume_reset_token(hash_reset_token(first.token), known_password[1])
    assert status == ResetTokenStatus.UNKNOWN


def test_new_request_purges_expired_links_of_other_users(
    settings: Settings, service: UserService, clock: FakeClock, read_table: ReadTable, make_user: MakeUser
) -> None:
    # Un enlace caducado es inútil: se borra en la siguiente petición de cualquiera.
    other, _ = make_user()
    user, _ = make_user()
    minutes = settings.password_reset_token_minutes
    service.request_password_reset(other.email, minutes, CLIENT_IP)

    clock.advance(minutes=minutes)
    service.request_password_reset(user.email, minutes, CLIENT_IP)

    assert [row["user_id"] for row in read_table(RESET_TOKENS_TABLE)] == [str(user.id)]


# --- Fallo del proveedor de email (FP4) ---


@pytest.mark.parametrize(
    ("sender", "error_class"),
    [
        pytest.param(
            FakeEmailSender(error=EmailDeliveryError("provider said: ana@example.invalid rejected")),
            "EmailDeliveryError",
            id="Resend falla",
        ),
        pytest.param(DisabledEmailSender(), "EmailNotConfiguredError", id="email sin configurar"),
    ],
)
def test_email_delivery_failure_is_logged_by_class_only_and_never_raises(
    settings: Settings, sender: EmailSender, error_class: str
) -> None:
    # La tarea corre tras responder: no puede lanzar, y el log no lleva ni el
    # destinatario ni el enlace ni el mensaje del proveedor (solo la clase, sin traza).
    pending = PendingResetEmail(email="ana@example.invalid", token="token-secreto-del-enlace")

    with capture_logs() as logs:
        send_reset_email(sender, settings, pending)

    api_records = [record for record in logs.records if record.name == "nexova.api"]
    assert [record.getMessage() for record in api_records] == [f"password reset email could not be delivered: {error_class}"]
    assert all(record.exc_info is None for record in api_records)
    assert "ana@example.invalid" not in logs.text() and pending.token not in logs.text()
