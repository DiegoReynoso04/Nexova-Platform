"""Aplicación FastAPI única del servicio: incidentes, gestor de incidencias, proveedores, autenticación e inventario.

Arranque: `uv run --env-file .env uvicorn app.main:create_app --factory` (ver README).
Sin JWT_SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES o DATABASE_URL la app no arranca
(ConfigError). Si la base del inventario no responde al arrancar, uvicorn no
arranca (`InventoryStartupError`, ver app/modules/inventory/database.py).

Solo ensambla: configuración, middlewares, handlers de error y routers.
"""

from typing import Any, Literal

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from reporting.router import router as reporting_router

from app.auth.dependencies import get_current_user
from app.auth.email import DisabledEmailSender, EmailSender, ResendEmailSender
from app.auth.repository import AuthRepository
from app.auth.service import UserService
from app.core.cache import ResponseCache
from app.core.config import Settings
from app.core.errors import InternalErrorMiddleware, install_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.core.telemetry import configure_telemetry_logger
from app.core.timing import configure_timing_logger, timing_middleware
from app.database import SupplierRepository
from app.modules.incident_manager.repository import IncidentRepository
from app.modules.incident_manager.router import drop_native_validation_responses
from app.modules.incident_manager.router import router as incident_manager_router
from app.modules.incidents.router import router as incidents_router
from app.modules.incidents.store import LastResultStore
from app.modules.inventory.database import build_engine, inventory_lifespan
from app.modules.inventory.router import router as inventory_router
from app.modules.telemetry.collector import EventRateLimiter
from app.modules.telemetry.router import TELEMETRY_EVENTS_PATH, TELEMETRY_MAX_BODY_BYTES
from app.modules.telemetry.router import router as telemetry_router
from app.modules.telemetry.stock_edit import StockEditReporter
from app.routes.auth import router as auth_router
from app.routes.profiles import router as profiles_router
from app.routes.suppliers import router as suppliers_router
from app.routes.users import router as users_router


class HealthResponse(BaseModel):
    """Respuesta de `GET /health`: técnica, sin datos (SPECS §3.3)."""

    status: Literal["ok"]


def build_email_sender(settings: Settings) -> EmailSender:
    """Resend si RESEND_API_KEY, EMAIL_FROM y PASSWORD_RESET_URL están definidas; si no, no se envían emails."""
    if settings.email_configured:
        return ResendEmailSender(settings.resend_api_key, settings.email_from)
    return DisabledEmailSender()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    settings.require_auth()
    settings.require_database()

    # El lifespan crea las tablas del inventario y activa RLS antes de aceptar peticiones.
    app = FastAPI(title="Nexova API", version="0.1.0", lifespan=inventory_lifespan)
    app.state.settings = settings
    # Inventario (Hito 5): motor SQLModel de la base PostgreSQL (Supabase). No conecta aquí.
    app.state.inventory_engine = build_engine(settings.database_url)
    # Un store por app: cada create_app() (y cada test) empieza sin análisis.
    app.state.result_store = LastResultStore()
    # TinyDB en disco: los proveedores persisten entre reinicios.
    app.state.supplier_repository = SupplierRepository(settings.suppliers_db_path)
    # User y Profile: TinyDB en un archivo propio (AUTH_DB_PATH).
    app.state.user_service = UserService(AuthRepository(settings.auth_db_path))
    # Gestor centralizado de incidencias: TinyDB en INCIDENTS_DB_PATH.
    app.state.incident_repository = IncidentRepository(settings.incidents_db_path)
    # Caché de lecturas (ticket de caching): en memoria, una por app; exige --workers 1.
    app.state.response_cache = ResponseCache()
    # AUTH-03: envío del enlace de restablecimiento (los tests lo sustituyen).
    app.state.email_sender = build_email_sender(settings)
    # Telemetría (P7): `direct_stock_edit_rejected` desde los handlers de error.
    app.state.stock_edit_reporter = StockEditReporter(settings, app.state.inventory_engine)
    # Throttle del colector (plan §7.2): en memoria, uno por app; exige --workers 1.
    app.state.telemetry_rate_limiter = EventRateLimiter()

    install_error_handlers(app)
    # Rutas existentes con datos sensibles: todas exigen un JWT válido (AUTH-01).
    authenticated = [Depends(get_current_user)]
    app.include_router(incidents_router, prefix="/api/incidents", dependencies=authenticated)
    # Gestor de incidencias: mismo prefijo, después del analizador. Sus rutas con id
    # usan el convertidor uuid, así que no capturan /analyze ni /results/export.
    app.include_router(incident_manager_router, prefix="/api/incidents", dependencies=authenticated)
    app.include_router(suppliers_router, prefix="/suppliers", dependencies=authenticated)
    # Inventario (Hito 5): el router ya lleva su prefijo `/inventory`.
    app.include_router(inventory_router, dependencies=authenticated)
    # Públicas: /auth/login, POST /users, /auth/forgot-password y /auth/reset-password;
    # el resto (incluida /auth/change-password) declara su propia dependencia.
    app.include_router(auth_router, prefix="/auth")
    app.include_router(users_router, prefix="/users")
    app.include_router(profiles_router, prefix="/profiles")
    # Colector de telemetría: público a propósito (sendBeacon no lleva
    # Authorization). Guarda en `telemetry_events`. Ver app/modules/telemetry/router.py.
    app.include_router(telemetry_router)
    configure_telemetry_logger()
    # Reporte de desempeño de negocio (services/reporting): GET con cualquier rol,
    # POST solo admin (lo declara la ruta).
    app.include_router(reporting_router, dependencies=authenticated)

    # OpenAPI del gestor de incidencias: sin el 422 que nunca responde (valida con 400).
    default_openapi = app.openapi

    def openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            drop_native_validation_responses(default_openapi(), app.routes)
        assert app.openapi_schema is not None
        return app.openapi_schema

    app.openapi = openapi  # type: ignore[method-assign]

    @app.get("/health", tags=["health"], response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    # add_middleware apila hacia fuera: el último añadido es el más externo.
    # Orden resultante: timing → CORS → errores internos (500) → límite de body → app.
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_upload_bytes,
        path_limits={TELEMETRY_EVENTS_PATH: TELEMETRY_MAX_BODY_BYTES},
    )
    app.add_middleware(InternalErrorMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        # PUT: el backoffice y el tracker editan el perfil con PUT /profiles/me (AUTH-02).
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        # El frontend enviará el JWT en `Authorization: Bearer <token>`.
        allow_headers=["Authorization"],
        allow_credentials=False,
        expose_headers=["Content-Disposition", "X-Analysis-Id"],
    )
    # Timing (ticket de caching, D8): el más externo, para medir la petición entera
    # (también los 500 que ya ha convertido InternalErrorMiddleware). REQUEST_TIMING_LOG=false lo quita.
    if settings.request_timing_log:
        configure_timing_logger()
        app.middleware("http")(timing_middleware)
    return app
