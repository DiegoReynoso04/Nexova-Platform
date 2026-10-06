"""Endpoints `/auth`: login con OAuth2 password flow y usuario actual (AUTH-01);
recuperación y cambio de contraseña (AUTH-03).
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.auth.dependencies import CurrentUserDep, EmailSenderDep, SettingsDep, UserServiceDep
from app.auth.email import EmailDeliveryError, EmailSender, password_reset_message, reset_link
from app.auth.models import (
    ChangePasswordRequest,
    CurrentUser,
    ForgotPasswordRequest,
    Message,
    ResetPasswordRequest,
    Token,
    normalize_email,
)
from app.auth.security import TOKEN_TYPE, burn_password_check, create_access_token, expires_in_seconds
from app.auth.service import PendingResetEmail
from app.core.config import Settings
from app.core.errors import InvalidCredentialsError, log_email_delivery_failure

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=Token)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], settings: SettingsDep, service: UserServiceDep
) -> Token:
    """Valida email + contraseña y devuelve un JWT de acceso.

    Formulario OAuth2 (`application/x-www-form-urlencoded`): el campo
    `username` es el **email**. Es lo que envía el botón "Authorize" de /docs.
    """
    try:
        email = normalize_email(form.username)
    except ValueError:
        burn_password_check(form.password)
        raise InvalidCredentialsError() from None
    user = service.authenticate(email, form.password)
    if user is None:
        raise InvalidCredentialsError()
    return Token(
        access_token=create_access_token(settings, str(user.id)),
        token_type=TOKEN_TYPE,
        expires_in=expires_in_seconds(settings),
    )


@router.get("/me", response_model=CurrentUser)
def read_current_user(current_user: CurrentUserDep, service: UserServiceDep) -> CurrentUser:
    """`email`, `role` y el `Profile` vinculado del usuario autenticado. Nunca credenciales."""
    profile = service.repository.get_profile(str(current_user.id))
    return CurrentUser(**current_user.public().model_dump(), profile=profile)


# AUTH-03. Respuesta idéntica exista o no el email (evita la enumeración de usuarios).
FORGOT_PASSWORD_DETAIL = "if that email is registered, a reset link has been sent"
PASSWORD_UPDATED_DETAIL = "password updated"


def client_ip(request: Request) -> str | None:
    """IP del cliente directo para la auditoría. No se leen cabeceras de proxy (`X-Forwarded-For`)."""
    return request.client.host if request.client else None


def send_reset_email(sender: EmailSender, settings: Settings, pending: PendingResetEmail) -> None:
    """Tarea en segundo plano: se ejecuta después de enviar la respuesta.

    Así el tiempo de respuesta no depende de si hubo que enviar un email, y un
    fallo del proveedor no cambia la respuesta (solo se registra el tipo de error).
    """
    message = password_reset_message(
        pending.email, reset_link(settings.password_reset_url, pending.token), settings.password_reset_token_minutes
    )
    try:
        sender.send(message)
    except EmailDeliveryError as exc:
        log_email_delivery_failure(exc)


@router.post("/forgot-password", response_model=Message)
def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: SettingsDep,
    service: UserServiceDep,
    sender: EmailSenderDep,
) -> Message:
    """Envía un enlace de restablecimiento si el email está registrado. Responde siempre 200."""
    pending = service.request_password_reset(payload.email, settings.password_reset_token_minutes, client_ip(request))
    if pending is not None:
        background_tasks.add_task(send_reset_email, sender, settings, pending)
    return Message(detail=FORGOT_PASSWORD_DETAIL)


@router.post("/reset-password", response_model=Message)
def reset_password(payload: ResetPasswordRequest, request: Request, service: UserServiceDep) -> Message:
    """Cambia la contraseña con el token del enlace. 400 si es inválido, expiró o ya se usó."""
    service.reset_password(payload.token, payload.new_password, client_ip(request))
    return Message(detail=PASSWORD_UPDATED_DETAIL)


@router.post("/change-password", response_model=Message)
def change_password(
    payload: ChangePasswordRequest, request: Request, current_user: CurrentUserDep, service: UserServiceDep
) -> Message:
    """Cambia la contraseña del usuario autenticado. 400 si la contraseña actual no coincide."""
    service.change_password(current_user, payload.current_password, payload.new_password, client_ip(request))
    return Message(detail=PASSWORD_UPDATED_DETAIL)
