"""Endpoints `/users` (AUTH-01): CRUD de credenciales.

Permisos: `POST` público; `GET /users` solo admin; `GET`/`PUT`/`DELETE
/users/{id}` el propio usuario o un admin (otro → 403). Solo un admin cambia
`role` y, desde AUTH-03, `password` (el resto usa `POST /auth/change-password`).
Ninguna respuesta incluye `hashed_password` (`response_model=UserRead`).
"""

from uuid import UUID

from fastapi import APIRouter, Response, status

from app.auth.dependencies import AdminDep, CurrentUserDep, UserServiceDep, ensure_self_or_admin
from app.auth.models import UserCreate, UserRead, UserRole, UserUpdate
from app.core.errors import ForbiddenError

router = APIRouter(tags=["users"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=UserRead)
def register_user(payload: UserCreate, service: UserServiceDep) -> UserRead:
    """Registro público. Crea el `User` (contraseña hasheada) y su `Profile`.

    `name`, `phone` y `address` son opcionales y van al `Profile`. El rol lo
    fija el backend (siempre `user`); enviar `role` responde 422.
    """
    user, _ = service.create_user(payload, role=UserRole.USER)
    return user.public()


@router.get("", response_model=list[UserRead])
def list_users(_: AdminDep, service: UserServiceDep) -> list[UserRead]:
    return [user.public() for user in service.list_users()]


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, current_user: CurrentUserDep, service: UserServiceDep) -> UserRead:
    ensure_self_or_admin(current_user, user_id)
    return service.get_user_by_id(str(user_id)).public()


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: UUID, payload: UserUpdate, current_user: CurrentUserDep, service: UserServiceDep) -> UserRead:
    """Cambia `email` (propio usuario o admin) y `password` y `role` (solo admin).

    Un usuario que no es admin cambia su contraseña solo con `POST
    /auth/change-password`, que exige la actual (AUTH-03): aquí, enviar
    `password` responde 403 y no se aplica ningún cambio.
    """
    ensure_self_or_admin(current_user, user_id)
    if payload.role is not None and current_user.role != UserRole.ADMIN:
        raise ForbiddenError("only an admin can change roles")
    if payload.password is not None and current_user.role != UserRole.ADMIN:
        raise ForbiddenError("use POST /auth/change-password to change your password")
    return service.update_user(str(user_id), payload).public()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_user(user_id: UUID, current_user: CurrentUserDep, service: UserServiceDep) -> Response:
    """Elimina el usuario y su `Profile` vinculado."""
    ensure_self_or_admin(current_user, user_id)
    service.delete_user(str(user_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
