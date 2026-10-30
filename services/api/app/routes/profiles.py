"""Endpoints `/profiles` (AUTH-01). El perfil es siempre el del usuario del token.

No se acepta ningún `user_id` del cliente: `ProfileUpdate` lo rechaza con 422
y el dueño lo determina `get_current_user`. Tampoco se devuelve: `ProfileRead`
no lleva `id` ni `user_id` (docs/serialization-audit.md, D2).
"""

from fastapi import APIRouter

from app.auth.dependencies import CurrentUserDep, UserServiceDep
from app.auth.models import ProfileRead, ProfileUpdate

router = APIRouter(tags=["profiles"])


@router.get("/me", response_model=ProfileRead)
def read_my_profile(current_user: CurrentUserDep, service: UserServiceDep) -> ProfileRead:
    return service.get_profile(str(current_user.id)).public()


@router.put("/me", response_model=ProfileRead)
def update_my_profile(payload: ProfileUpdate, current_user: CurrentUserDep, service: UserServiceDep) -> ProfileRead:
    """Actualiza `name`, `phone` y `address` (solo los campos enviados)."""
    return service.update_profile(str(current_user.id), payload).public()
