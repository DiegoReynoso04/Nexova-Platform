"""Dependencias de autenticación y autorización (AUTH-01).

- `get_current_user`: dependencia reutilizable. Extrae `Authorization: Bearer
  <token>` (vía `OAuth2PasswordBearer`), valida firma y expiración del JWT y
  recupera el usuario de TinyDB por el `sub`. Cualquier fallo → 401.
- `require_admin` y `ensure_self_or_admin`: autenticado pero sin permiso → 403.

Para proteger un router completo: `include_router(..., dependencies=[Depends(get_current_user)])`
(así se protegen `/suppliers` y `/api/incidents`, ver `app/main.py`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from app.auth.email import EmailSender
from app.auth.models import UserInDB, UserRole
from app.auth.security import decode_access_token
from app.auth.service import UserService
from app.core.config import Settings
from app.core.errors import ForbiddenError, NotAuthenticatedError

# `tokenUrl` hace que el botón "Authorize" de /docs haga login en POST /auth/login.
# `auto_error=False`: el 401 lo lanza `get_current_user` con el formato de error
# de la API (`{detail, code}` + `WWW-Authenticate: Bearer`).
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def get_settings(request: Request) -> Settings:
    settings = request.app.state.settings
    assert isinstance(settings, Settings)
    return settings


def get_user_service(request: Request) -> UserService:
    service = request.app.state.user_service
    assert isinstance(service, UserService)
    return service


def get_email_sender(request: Request) -> EmailSender:
    sender: EmailSender = request.app.state.email_sender
    return sender


SettingsDep = Annotated[Settings, Depends(get_settings)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)], settings: SettingsDep, service: UserServiceDep
) -> UserInDB:
    """Usuario autenticado por el JWT. 401 si falta, está mal formado, expiró o el usuario no existe."""
    if not token:
        raise NotAuthenticatedError()
    user_id = decode_access_token(settings, token)
    if user_id is None:
        raise NotAuthenticatedError()
    user = service.repository.get_user(user_id)
    if user is None or not user.is_active:
        raise NotAuthenticatedError()
    return user


CurrentUserDep = Annotated[UserInDB, Depends(get_current_user)]


def require_admin(current_user: CurrentUserDep) -> UserInDB:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenError("admin role required")
    return current_user


AdminDep = Annotated[UserInDB, Depends(require_admin)]


def ensure_self_or_admin(current_user: UserInDB, user_id: UUID) -> None:
    """403 si el usuario autenticado intenta acceder a otro usuario sin ser admin.

    Se comprueba antes de buscar el recurso: un no-admin recibe 403 tanto si
    el otro usuario existe como si no (no se revela qué ids existen).
    """
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise ForbiddenError()
