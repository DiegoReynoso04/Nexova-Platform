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
# Archivo TinyDB del gestor centralizado de incidencias (incidencias + claves del seed).
DEFAULT_INCIDENTS_DB_PATH = SERVICE_ROOT / "data" / "incidents.json"
# HS256 necesita una clave de al menos 256 bits; se exige en caracteres.
MIN_JWT_SECRET_LENGTH = 32
# Tope TÉCNICO de ACCESS_TOKEN_EXPIRE_MINUTES (1 año), no una política de sesión:
# con valores enormes `iat + minutos` se sale del rango de datetime y cada login
# fallaba (OverflowError al firmar el token) aunque la API hubiera arrancado.
# La duración máxima de negocio de la sesión no la fija ningún documento: la decide el CTO.
MAX_ACCESS_TOKEN_EXPIRE_MINUTES = 525_600
# AUTH-03: vigencia del enlace de restablecimiento. El ticket fija 15–60 minutos.
DEFAULT_PASSWORD_RESET_TOKEN_MINUTES = 30
MIN_PASSWORD_RESET_TOKEN_MINUTES = 15
MAX_PASSWORD_RESET_TOKEN_MINUTES = 60
# Hito 5: esquemas de DATABASE_URL aceptados desde el entorno (Supabase, PostgreSQL
# con psycopg2). Los tests inyectan `Settings(database_url="sqlite://")` sin pasar por aquí.
DATABASE_URL_SCHEMES = ("postgresql", "postgresql+psycopg2")
# Ticket de caching (D8): valores aceptados por REQUEST_TIMING_LOG.
TRUE_VALUES = ("true", "1", "yes", "on")
FALSE_VALUES = ("false", "0", "no", "off")
# Telemetría (ticket de captura): esquemas de TELEMETRY_ENDPOINT si es una URL absoluta.
TELEMETRY_ENDPOINT_SCHEMES = ("http://", "https://")
# Plan de telemetría, D4: mínimo de stock por defecto (sin columna por activo hasta P2).
DEFAULT_INVENTORY_MIN_STOCK = 5
# P9: clave HMAC del proveedor; mismo mínimo que la del JWT.
MIN_TELEMETRY_SUPPLIER_KEY_LENGTH = 32
# P10 (D3): umbral de variación del coste (%) y número de entradas de referencia.
DEFAULT_COST_VARIANCE_THRESHOLD_PCT = 10.0
MAX_COST_VARIANCE_THRESHOLD_PCT = 1000.0
DEFAULT_COST_VARIANCE_WINDOW = 3
MAX_COST_VARIANCE_WINDOW = 100


class ConfigError(ValueError):
    """Variable de entorno inválida. Se lanza al arrancar, no en una petición."""


@dataclass(frozen=True, slots=True)
class Settings:
    cors_allowed_origins: tuple[str, ...] = DEFAULT_CORS_ALLOWED_ORIGINS
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    suppliers_db_path: Path = DEFAULT_SUPPLIERS_DB_PATH
    auth_db_path: Path = DEFAULT_AUTH_DB_PATH
    incidents_db_path: Path = DEFAULT_INCIDENTS_DB_PATH
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
    # Hito 5: base PostgreSQL (Supabase) del inventario. Sin valor por defecto:
    # `require_database()` la exige al arrancar la API. Lleva la contraseña de la
    # base, así que nunca aparece en un repr/log ni en un mensaje de error.
    database_url: str = field(default="", repr=False)
    # Middleware de timing (ticket de caching, D8): una línea por petición en
    # `api.timing`, sin `/health`. Activo por defecto; REQUEST_TIMING_LOG=false lo apaga.
    request_timing_log: bool = True
    # Telemetría (ticket de captura): destino de los eventos, declarado desde el
    # stub para fijar el patrón. Hoy no se usa: la ruta del colector es siempre
    # `/telemetry/events` (contrato del plan), y el frontend lee la suya de
    # NEXT_PUBLIC_TELEMETRY_ENDPOINT. Opcional: vacío = sin destino propio.
    telemetry_endpoint: str = ""
    # Mínimo de stock con el que una salida dispara `stock_threshold_triggered`
    # (plan D4, `<`). El mismo para todos los activos hasta que exista
    # `Asset.min_stock` (P2). Con 0 no se dispara nunca.
    inventory_default_min_stock: int = DEFAULT_INVENTORY_MIN_STOCK
    # P9: clave del HMAC del proveedor (`supplier_key`). Opcional: sin ella las
    # entradas no llevan `supplier_key` y el frontend no emite los eventos que
    # lo necesitan. Es un secreto: nunca en un repr/log.
    telemetry_supplier_key: str = field(default="", repr=False)
    # P10: una entrada se desvía si |variación| > umbral frente a la media de
    # las `window` entradas anteriores con coste del mismo activo y proveedor.
    cost_variance_threshold_pct: float = DEFAULT_COST_VARIANCE_THRESHOLD_PCT
    cost_variance_window: int = DEFAULT_COST_VARIANCE_WINDOW

    def __post_init__(self) -> None:
        if "*" in self.cors_allowed_origins:
            raise ConfigError("CORS_ALLOWED_ORIGINS must list explicit origins; '*' is not allowed")
        if self.max_upload_bytes <= 0:
            raise ConfigError("MAX_UPLOAD_BYTES must be a positive integer")
        if self.access_token_expire_minutes is not None and not (
            1 <= self.access_token_expire_minutes <= MAX_ACCESS_TOKEN_EXPIRE_MINUTES
        ):
            raise ConfigError(f"ACCESS_TOKEN_EXPIRE_MINUTES must be between 1 and {MAX_ACCESS_TOKEN_EXPIRE_MINUTES}")
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
        if self.telemetry_endpoint and not (
            self.telemetry_endpoint.startswith(TELEMETRY_ENDPOINT_SCHEMES) or self.telemetry_endpoint.startswith("/")
        ):
            raise ConfigError("TELEMETRY_ENDPOINT must be an absolute http(s) URL or a path starting with /")
        if self.inventory_default_min_stock < 0:
            raise ConfigError("INVENTORY_DEFAULT_MIN_STOCK must be a non-negative integer")
        if self.telemetry_supplier_key and len(self.telemetry_supplier_key) < MIN_TELEMETRY_SUPPLIER_KEY_LENGTH:
            raise ConfigError(
                f"TELEMETRY_SUPPLIER_KEY must have at least {MIN_TELEMETRY_SUPPLIER_KEY_LENGTH} characters"
            )
        if not (0 < self.cost_variance_threshold_pct <= MAX_COST_VARIANCE_THRESHOLD_PCT):
            raise ConfigError(
                f"TELEMETRY_COST_VARIANCE_THRESHOLD_PCT must be greater than 0 and at most {MAX_COST_VARIANCE_THRESHOLD_PCT:g}"
            )
        if not (1 <= self.cost_variance_window <= MAX_COST_VARIANCE_WINDOW):
            raise ConfigError(f"TELEMETRY_COST_VARIANCE_WINDOW must be between 1 and {MAX_COST_VARIANCE_WINDOW}")

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

    def require_database(self) -> None:
        """Lo llama `create_app` después de `require_auth`: la API no arranca sin DATABASE_URL.

        No valida el esquema (eso lo hace `from_env`) para que los tests puedan
        inyectar SQLite. El seeder de proveedores y `create-admin` no lo llaman.
        """
        if not self.database_url:
            raise ConfigError("DATABASE_URL is required (see services/api/.env.example)")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Settings":
        origins = environ.get("CORS_ALLOWED_ORIGINS")
        max_upload = environ.get("MAX_UPLOAD_BYTES")
        suppliers_db_path = environ.get("SUPPLIERS_DB_PATH", "").strip()
        auth_db_path = environ.get("AUTH_DB_PATH", "").strip()
        incidents_db_path = environ.get("INCIDENTS_DB_PATH", "").strip()
        expire_minutes = environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
        reset_minutes = environ.get("PASSWORD_RESET_TOKEN_EXPIRE_MINUTES", "").strip()
        database_url = environ.get("DATABASE_URL", "").strip()
        timing_log = environ.get("REQUEST_TIMING_LOG", "").strip().lower()
        if timing_log and timing_log not in TRUE_VALUES + FALSE_VALUES:
            raise ConfigError("REQUEST_TIMING_LOG must be true or false")
        # Solo se mira lo que va antes de "://"; el mensaje nunca repite la URL.
        scheme, separator, _ = database_url.partition("://")
        if database_url and (not separator or scheme not in DATABASE_URL_SCHEMES):
            raise ConfigError("DATABASE_URL must use the postgresql:// or postgresql+psycopg2:// scheme")
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
        min_stock = environ.get("INVENTORY_DEFAULT_MIN_STOCK", "").strip()
        threshold = environ.get("TELEMETRY_COST_VARIANCE_THRESHOLD_PCT", "").strip()
        window = environ.get("TELEMETRY_COST_VARIANCE_WINDOW", "").strip()
        try:
            inventory_default_min_stock = int(min_stock) if min_stock else DEFAULT_INVENTORY_MIN_STOCK
        except ValueError:
            raise ConfigError("INVENTORY_DEFAULT_MIN_STOCK must be a non-negative integer") from None
        try:
            cost_variance_threshold_pct = float(threshold) if threshold else DEFAULT_COST_VARIANCE_THRESHOLD_PCT
        except ValueError:
            raise ConfigError("TELEMETRY_COST_VARIANCE_THRESHOLD_PCT must be a number") from None
        try:
            cost_variance_window = int(window) if window else DEFAULT_COST_VARIANCE_WINDOW
        except ValueError:
            raise ConfigError("TELEMETRY_COST_VARIANCE_WINDOW must be an integer") from None
        return cls(
            cors_allowed_origins=(
                tuple(origin.strip() for origin in origins.split(",") if origin.strip())
                if origins is not None
                else DEFAULT_CORS_ALLOWED_ORIGINS
            ),
            max_upload_bytes=max_upload_bytes,
            suppliers_db_path=Path(suppliers_db_path) if suppliers_db_path else DEFAULT_SUPPLIERS_DB_PATH,
            auth_db_path=Path(auth_db_path) if auth_db_path else DEFAULT_AUTH_DB_PATH,
            incidents_db_path=Path(incidents_db_path) if incidents_db_path else DEFAULT_INCIDENTS_DB_PATH,
            jwt_secret_key=environ.get("JWT_SECRET_KEY", "").strip(),
            access_token_expire_minutes=access_token_expire_minutes,
            resend_api_key=environ.get("RESEND_API_KEY", "").strip(),
            email_from=environ.get("EMAIL_FROM", "").strip(),
            password_reset_url=environ.get("PASSWORD_RESET_URL", "").strip(),
            password_reset_token_minutes=password_reset_token_minutes,
            database_url=database_url,
            request_timing_log=timing_log not in FALSE_VALUES,
            telemetry_endpoint=environ.get("TELEMETRY_ENDPOINT", "").strip(),
            inventory_default_min_stock=inventory_default_min_stock,
            telemetry_supplier_key=environ.get("TELEMETRY_SUPPLIER_KEY", "").strip(),
            cost_variance_threshold_pct=cost_variance_threshold_pct,
            cost_variance_window=cost_variance_window,
        )
