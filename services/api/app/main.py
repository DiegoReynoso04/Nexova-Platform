"""Aplicación FastAPI única del servicio: incidentes, proveedores y autenticación.

Arranque: `uv run --env-file .env uvicorn app.main:create_app --factory` (ver README).
Sin JWT_SECRET_KEY o ACCESS_TOKEN_EXPIRE_MINUTES la app no arranca (ConfigError).

Solo ensambla: configuración, middlewares, handlers de error y routers.
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.dependencies import get_current_user
from app.auth.email import DisabledEmailSender, EmailSender, ResendEmailSender
from app.auth.repository import AuthRepository
from app.auth.service import UserService
from app.core.config import Settings
from app.core.errors import InternalErrorMiddleware, install_error_handlers
from app.core.limits import BodySizeLimitMiddleware
from app.database import SupplierRepository
from app.modules.incidents.router import router as incidents_router
from app.modules.incidents.store import LastResultStore
from app.routes.auth import router as auth_router
from app.routes.profiles import router as profiles_router
from app.routes.suppliers import router as suppliers_router
from app.routes.users import router as users_router


def build_email_sender(settings: Settings) -> EmailSender:
    """Resend si RESEND_API_KEY, EMAIL_FROM y PASSWORD_RESET_URL están definidas; si no, no se envían emails."""
    if settings.email_configured:
        return ResendEmailSender(settings.resend_api_key, settings.email_from)
    return DisabledEmailSender()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    settings.require_auth()

    app = FastAPI(title="Nexova API", version="0.1.0")
    app.state.settings = settings
    # Un store por app: cada create_app() (y cada test) empieza sin análisis.
    app.state.result_store = LastResultStore()
    # TinyDB en disco: los proveedores persisten entre reinicios.
    app.state.supplier_repository = SupplierRepository(settings.suppliers_db_path)
    # User y Profile: TinyDB en un archivo propio (AUTH_DB_PATH).
    app.state.user_service = UserService(AuthRepository(settings.auth_db_path))
    # AUTH-03: envío del enlace de restablecimiento (los tests lo sustituyen).
    app.state.email_sender = build_email_sender(settings)

    install_error_handlers(app)
    # Rutas existentes con datos sensibles: todas exigen un JWT válido (AUTH-01).
    authenticated = [Depends(get_current_user)]
    app.include_router(incidents_router, prefix="/api/incidents", dependencies=authenticated)
    app.include_router(suppliers_router, prefix="/suppliers", dependencies=authenticated)
    # Públicas: /auth/login, POST /users, /auth/forgot-password y /auth/reset-password;
    # el resto (incluida /auth/change-password) declara su propia dependencia.
    app.include_router(auth_router, prefix="/auth")
    app.include_router(users_router, prefix="/users")
    app.include_router(profiles_router, prefix="/profiles")

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # add_middleware apila hacia fuera: el último añadido es el más externo.
    # Orden resultante: CORS → errores internos (500) → límite de body → app.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
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
    return app
