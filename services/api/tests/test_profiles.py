"""`/profiles/me`: el perfil del usuario autenticado y cómo se actualiza.

Unidades: las funciones de ruta `read_my_profile` y `update_my_profile`
(`app/routes/profiles.py`), `UserService.get_profile`/`update_profile` y las
reglas de `ProfileUpdate`. Sin HTTP. El dueño del perfil es siempre el
usuario del token: el cliente no puede elegirlo (SPECS §18).
"""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.auth.models import ProfileUpdate
from app.auth.service import UserService
from app.core.errors import ProfileNotFoundError
from app.routes.profiles import read_my_profile, update_my_profile

from .conftest import MakeUser


# --- Camino feliz (P1) ---


def test_user_reads_its_own_profile(service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user(name="Ana", phone="000 000 000")
    profile = read_my_profile(user, service)
    # Sin `id` ni `user_id` (auditoría de serialización, D2): el dueño es siempre el del token.
    assert profile.model_dump() == {"name": "Ana", "phone": "000 000 000", "address": None}


def test_profile_update_changes_only_the_fields_sent(service: UserService, make_user: MakeUser) -> None:
    # D-AUTH-13: semántica parcial; lo que no se envía se conserva.
    user, _ = make_user(name="Ana", phone="000 000 000")

    profile = update_my_profile(ProfileUpdate(address="Calle Ejemplo 1"), user, service)

    assert (profile.name, profile.phone, profile.address) == ("Ana", "000 000 000", "Calle Ejemplo 1")
    assert read_my_profile(user, service) == profile


# --- Límites (P2) ---


def test_sending_null_clears_a_field(service: UserService, make_user: MakeUser) -> None:
    # `null` explícito borra el dato; omitir el campo lo conserva.
    user, _ = make_user(name="Ana", phone="000 000 000")
    profile = update_my_profile(ProfileUpdate(phone=None), user, service)
    assert (profile.name, profile.phone) == ("Ana", None)


def test_empty_update_leaves_the_profile_unchanged(service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user(name="Ana")
    before = read_my_profile(user, service)
    assert update_my_profile(ProfileUpdate(), user, service) == before


def test_profile_text_is_trimmed_and_limited_to_200_characters(service: UserService, make_user: MakeUser) -> None:
    user, _ = make_user()

    profile = update_my_profile(ProfileUpdate(name=f"  {'a' * 200}  "), user, service)

    assert profile.name == "a" * 200
    with pytest.raises(ValidationError) as exc:
        ProfileUpdate(name="a" * 201)
    assert [error["loc"] for error in exc.value.errors()] == [("name",)]


# --- Modos de fallo (P3, P4) ---


@pytest.mark.parametrize("field", ["user_id", "id", "email"])
def test_profile_update_rejects_fields_outside_the_profile(field: str) -> None:
    # Sin `user_id` del cliente nadie puede escribir en el perfil de otro.
    with pytest.raises(ValidationError) as exc:
        ProfileUpdate.model_validate({"name": "Ana", field: "x"})
    assert [(error["loc"], error["type"]) for error in exc.value.errors()] == [((field,), "extra_forbidden")]


@pytest.mark.parametrize(
    "payload",
    [pytest.param({}, id="cuerpo vacío"), pytest.param({"name": "Ana"}, id="con datos")],
)
def test_user_without_profile_gets_profile_not_found(
    service: UserService, make_user: MakeUser, drop_profile: Callable[[str], None], payload: dict[str, str]
) -> None:
    # Un usuario sin perfil (estado que la API no produce) recibe 404, y el PUT
    # no crea un perfil nuevo por su cuenta.
    user, _ = make_user()
    drop_profile(str(user.id))

    with pytest.raises(ProfileNotFoundError):
        read_my_profile(user, service)
    with pytest.raises(ProfileNotFoundError):
        update_my_profile(ProfileUpdate.model_validate(payload), user, service)
    assert service.repository.get_profile(str(user.id)) is None
