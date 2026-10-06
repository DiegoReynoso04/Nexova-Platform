"""Configuración del servicio, leída una sola vez de variables de entorno.

Sin pydantic-settings ni python-dotenv (no autorizados): la API no carga
archivos `.env`; `.env.example` solo documenta las variables.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CORS_ALLOWED_ORIGINS = ("http://localhost:3000",)
# 1 MiB. Decisión técnica de esta API (D-API-4), no un requisito del contexto
# de Nexova. Con este valor el multipart nunca supera el umbral a partir del
# cual Starlette vuelca el archivo a disco (SpooledTemporaryFile de 1 MiB).
DEFAULT_MAX_UPLOAD_BYTES = 1024 * 1024
# Archivo TinyDB del directorio de proveedores: services/api/data/ (ignorado por git).
SERVICE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SUPPLIERS_DB_PATH = SERVICE_ROOT / "data" / "suppliers.json"
# Archivo TinyDB de usuarios y perfiles (AUTH-01), separado del de proveedores.
DEFAULT_AUTH_DB_PATH = SERVICE_ROOT / "data" / "auth.json"
# HS256 necesita una clave de al menos 256 bits; se exige en caracteres.
MIN_JWT_SECRET_LENGTH = 32
# AUTH-03: vigencia del enlace de restablecimiento. El ticket fija 15–60 minutos.
DEFAULT_PASSWORD_RESET_TOKEN_MINUTES = 30
MIN_PASSWORD_RESET_TOKEN_MINUTES = 15
MAX_PASSWORD_RESET_TOKEN_MINUTES = 60


class ConfigError(ValueError):
    """Variable de entorno inválida. Se lanza al arrancar, no en una petición."""


@dataclass(frozen=True, slots=True)
class Settings:
    cors_allowed_origins: tuple[str, ...] = DEFAULT_CORS_ALLOWED_ORIGINS
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    suppliers_db_path: Path = DEFAULT_SUPPLIERS_DB_PATH
    auth_db_path: Path = DEFAULT_AUTH_DB_PATH
    # Sin valores por defecto a propósito: vienen siempre del entorno
    # (JWT_SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES) y `require_auth()` los exige
    # al arrancar la API. `repr=False`: la clave nunca aparece en un repr/log.
    jwt_secret_key: str = field(default="", repr=False)
    access_token_expire_minutes: int | None = None
    # AUTH-03: envío del enlace de restablecimiento con Resend. Opcional al
    # arrancar: sin las tres variables la API funciona, pero no envía emails
    # (ver `email_configured`). La API key nunca aparece en un repr/log.
    resend_api_key: str = field(default="", repr=False)
    email_from: str = ""
    password_reset_url: str = ""
    password_reset_token_minutes: int = DEFAULT_PASSWORD_RESET_TOKEN_MINUTES

    def __post_init__(self) -> None:
        if "*" in self.cors_allowed_origins:
            raise ConfigError("CORS_ALLOWED_ORIGINS must list explicit origins; '*' is not allowed")
        if self.max_upload_bytes <= 0:
            raise ConfigError("MAX_UPLOAD_BYTES must be a positive integer")
        if self.access_token_expire_minutes is not None and self.access_token_expire_minutes <= 0:
            raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer")
        if not (
            MIN_PASSWORD_RESET_TOKEN_MINUTES <= self.password_reset_token_minutes <= MAX_PASSWORD_RESET_TOKEN_MINUTES
        ):
            raise ConfigError(
                f"PASSWORD_RESET_TOKEN_EXPIRE_MINUTES must be between {MIN_PASSWORD_RESET_TOKEN_MINUTES} "
                f"and {MAX_PASSWORD_RESET_TOKEN_MINUTES}"
            )
        email_settings = (self.resend_api_key, self.email_from, self.password_reset_url)
        if any(email_settings) and not all(email_settings):
            raise ConfigError(
                "RESEND_API_KEY, EMAIL_FROM and PASSWORD_RESET_URL must be set together "
                "(see services/api/.env.example)"
            )
        if self.password_reset_url and not self.password_reset_url.startswith(("http://", "https://")):
            raise ConfigError("PASSWORD_RESET_URL must be an absolute http(s) URL")

    @property
    def email_configured(self) -> bool:
        """Hay proveedor de email: `POST /auth/forgot-password` envía el enlace."""
        return bool(self.resend_api_key)

    def require_auth(self) -> None:
        """Lo llama `create_app`: la API no arranca sin la configuración del JWT.

        El seeder y `create-admin` no lo llaman: no firman tokens.
        """
        if len(self.jwt_secret_key) < MIN_JWT_SECRET_LENGTH:
            raise ConfigError(
                f"JWT_SECRET_KEY is required and must have at least {MIN_JWT_SECRET_LENGTH} characters "
                "(see services/api/.env.example)"
            )
        if self.access_token_expire_minutes is None:
            raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES is required (see services/api/.env.example)")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Settings":
        origins = environ.get("CORS_ALLOWED_ORIGINS")
        max_upload = environ.get("MAX_UPLOAD_BYTES")
        suppliers_db_path = environ.get("SUPPLIERS_DB_PATH", "").strip()
        auth_db_path = environ.get("AUTH_DB_PATH", "").strip()
        expire_minutes = environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
        reset_minutes = environ.get("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "").strip()
        try:
            max_upload_bytes = int(max_upload) if max_upload is not None else DEFAULT_MAX_UPLOAD_BYTES
        except ValueError:
            raise ConfigError("MAX_UPLOAD_BYTES must be a positive integer") from None
        try:
            access_token_expire_minutes = int(expire_minutes) if expire_minutes else None
        except ValueError:
            raise ConfigError("ACCESS_TOKEN_EXPIRE_MINUTES must be a positive integer") from None
        try:
            password_reset_token_minutes = int(reset_minutes) if reset_minutes else DEFAULT_PASSWORD_RESET_TOKEN_MINUTES
        except ValueError:
            raise ConfigError("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES must be an integer") from None
        return cls(
            cors_allowed_origins=(
                tuple(origin.strip() for origin in origins.split(",") if origin.strip())
                if origins is not None
                else DEFAULT_CORS_ALLOWED_ORIGINS
            ),
            max_upload_bytes=max_upload_bytes,
            suppliers_db_path=Path(suppliers_db_path) if suppliers_db_path else DEFAULT_SUPPLIERS_DB_PATH,
            auth_db_path=Path(auth_db_path) if auth_db_path else DEFAULT_AUTH_DB_PATH,
            jwt_secret_key=environ.get("JWT_SECRET_KEY", "").strip(),
            access_token_expire_minutes=access_token_expire_minutes,
            resend_api_key=environ.get("RESEND_API_KEY", "").strip(),
            email_from=environ.get("EMAIL_FROM", "").strip(),
            password_reset_url=environ.get("PASSWORD_RESET_URL", "").strip(),
            password_reset_token_minutes=password_reset_token_minutes,
        )
