"""Modelos Pydantic de usuarios y perfiles (AUTH-01).

- `User` guarda solo credenciales: `id`, `email`, `hashed_password`,
  `is_active`, `role`, `created_at`. Nombre y datos de contacto viven en
  `Profile` (`id`, `user_id`, `name`, `phone`, `address`), uno a uno con `User`.
- `UserInDB` es el único modelo con `hashed_password` y nunca es el
  `response_model` de una ruta: las respuestas usan `UserRead`/`CurrentUser`.
- Los modelos de entrada usan `extra="forbid"`: un campo no previsto
  (p. ej. `hashed_password`, `user_id` o `is_active`) responde 422.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, StringConstraints

# Límite de bcrypt: solo usa los primeros 72 bytes. Se valida antes del hash
# para no aceptar contraseñas que se truncarían en silencio.
BCRYPT_MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8
# RFC 5321: 254 caracteres como máximo en una dirección utilizable.
MAX_EMAIL_LENGTH = 254


class UserRole(StrEnum):
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"


def normalize_email(value: str) -> str:
    """Valida un email sencillo y lo normaliza (sin espacios y en minúsculas).

    Sin dependencias (email-validator no está autorizada) y sin regex: una
    sola arroba, parte local y dominio no vacíos, dominio con al menos un
    punto interior y sin espacios ni puntos consecutivos.
    """
    email = value.strip().lower()
    local, separator, domain = email.partition("@")
    labels = domain.split(".")
    if (
        not separator
        or not local
        or len(email) > MAX_EMAIL_LENGTH
        or "@" in domain
        or any(character.isspace() for character in email)
        or len(labels) < 2
        or not all(labels)
    ):
        raise ValueError("email must be a valid email address")
    return email


def _check_password(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"password must have at least {MIN_PASSWORD_LENGTH} characters")
    if len(value.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes long (bcrypt limit)")
    return value


Email = Annotated[str, AfterValidator(normalize_email)]
Password = Annotated[str, AfterValidator(_check_password)]
# Datos de perfil opcionales (`null` = sin dato), sin espacios en los extremos.
ProfileText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class ProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: ProfileText | None = None
    phone: ProfileText | None = None
    address: ProfileText | None = None


class UserCreate(ProfileFields):
    """Entrada de `POST /users`: `email`, `password` y perfil inicial opcional.

    No admite `role` (422 por `extra="forbid"`): el registro público crea
    siempre `role=user`. Los roles los asigna un admin con `PUT /users/{id}`;
    el primer admin se crea con `uv run create-admin`.
    """

    email: Email
    password: Password


class UserUpdate(BaseModel):
    """Entrada de `PUT /users/{id}`. Solo se cambian los campos enviados."""

    model_config = ConfigDict(extra="forbid")

    email: Email | None = None
    password: Password | None = None
    role: UserRole | None = None


class ProfileUpdate(ProfileFields):
    """Entrada de `PUT /profiles/me`. No admite `user_id`: el dueño lo fija el token."""


class UserRead(BaseModel):
    """`User` tal como sale por la API: nunca incluye `hashed_password`."""

    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserInDB(UserRead):
    """Documento completo de TinyDB. Solo para uso interno (login y servicios)."""

    hashed_password: str

    def public(self) -> UserRead:
        return UserRead.model_validate(self.model_dump(exclude={"hashed_password"}))


class Profile(BaseModel):
    id: UUID
    user_id: UUID
    name: str | None = None
    phone: str | None = None
    address: str | None = None


class CurrentUser(UserRead):
    """Respuesta de `GET /auth/me`: credenciales públicas + perfil vinculado."""

    profile: Profile | None


class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


# AUTH-03: recuperación y cambio de contraseña.
# Límite generoso para la contraseña actual y el token: solo evita cuerpos
# desmesurados; la validez real la decide la comparación con el hash.
MAX_SECRET_INPUT_LENGTH = 512


class ForgotPasswordRequest(BaseModel):
    """Entrada de `POST /auth/forgot-password`."""

    model_config = ConfigDict(extra="forbid")

    email: Email


class ResetPasswordRequest(BaseModel):
    """Entrada de `POST /auth/reset-password`: token del enlace + contraseña nueva."""

    model_config = ConfigDict(extra="forbid")

    token: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SECRET_INPUT_LENGTH)]
    new_password: Password


class ChangePasswordRequest(BaseModel):
    """Entrada de `POST /auth/change-password` (requiere sesión)."""

    model_config = ConfigDict(extra="forbid")

    current_password: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SECRET_INPUT_LENGTH)]
    new_password: Password


class Message(BaseModel):
    """Respuesta de las rutas de contraseña: un mensaje fijo, sin datos del usuario."""

    detail: str


class AuditEvent(StrEnum):
    """Eventos de contraseña registrados en la tabla `password_audit` (AUTH-03, opcional del ticket)."""

    RESET_REQUESTED = "reset_requested"
    RESET_COMPLETED = "reset_completed"
    RESET_REJECTED = "reset_rejected"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_CHANGE_REJECTED = "password_change_rejected"
