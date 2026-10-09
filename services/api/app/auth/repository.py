"""Acceso a TinyDB para `User` y `Profile` (AUTH-01). Única capa que toca esa base.

Un archivo propio (`Settings.auth_db_path`, por defecto
`services/api/data/auth.json`, ignorado por git), separado del de proveedores,
con dos tablas: `users` y `profiles`. User y Profile viven solo aquí: no hay
tablas de usuarios ni perfiles en ninguna otra base.

Identidad: `User.id` y `Profile.id` son UUID v4 generados por el sistema y
guardados como campo del documento. No se usa el `doc_id` interno de TinyDB
(entero y dependiente del archivo) para que el `id` sea estable, viaje en el
JWT (`sub`) y otros módulos puedan referenciarlo como `user_uuid`.
`Profile.user_id` = `User.id`.

Mismo patrón que `SupplierRepository`: `threading.Lock` + la base se abre y se
cierra en cada operación; exige un único worker. Crear un usuario inserta su
perfil en la misma operación y borrarlo borra también su perfil.

AUTH-03 añade dos tablas al mismo archivo:
- `password_reset_tokens`: `id`, `user_id`, `token_hash` (SHA-256, nunca el
  token en claro), `created_at`, `expires_at` y `used_at` (`null` hasta que se
  usa). Validar, cambiar la contraseña y marcar el token como usado ocurre en
  una sola operación bajo el lock: un token no puede usarse dos veces.
- `password_audit`: `id`, `event`, `user_id` (`null` si el email no existe),
  `ip`, `reason` y `created_at`. Nunca el email, el token ni contraseñas.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from enum import StrEnum
from typing import Any
from uuid import uuid4

from tinydb import Query, TinyDB
from tinydb.table import Document, Table

from app.auth.models import AuditEvent, Profile, ProfileFields, UserInDB, UserRole
from app.core.storage import GuardedJSONStorage, Store

USERS_TABLE = "users"
PROFILES_TABLE = "profiles"
RESET_TOKENS_TABLE = "password_reset_tokens"
AUDIT_TABLE = "password_audit"


class ResetTokenStatus(StrEnum):
    """Resultado de `consume_reset_token`. Solo `VALID` cambia la contraseña."""

    VALID = "valid"
    UNKNOWN = "unknown"
    EXPIRED = "expired"
    USED = "used"


class DuplicateEmailError(Exception):
    """Ya existe un usuario con ese email (se traduce a 409 en el servicio)."""


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuthRepository:
    def __init__(self, path: Path, clock: Callable[[], datetime] = utc_now) -> None:
        self.path = path
        self._clock = clock
        self._lock = threading.Lock()

    def now(self) -> datetime:
        return self._clock()

    def _open(self) -> TinyDB:
        # Un archivo ilegible o corrupto responde 503 (GuardedJSONStorage).
        return TinyDB(self.path, storage=GuardedJSONStorage, store=Store.AUTH, create_dirs=True, encoding="utf-8", indent=2)

    @contextmanager
    def _db(self) -> Iterator[TinyDB]:
        with self._lock, self._open() as db:
            yield db

    @contextmanager
    def _tables(self) -> Iterator[tuple[Table, Table]]:
        with self._lock, self._open() as db:
            yield db.table(USERS_TABLE), db.table(PROFILES_TABLE)

    def create_user(
        self, email: str, hashed_password: str, role: UserRole, profile: ProfileFields
    ) -> tuple[UserInDB, Profile]:
        """Inserta el usuario y su perfil. `hashed_password` ya viene hasheado."""
        user_record: dict[str, Any] = {
            "id": str(uuid4()),
            "email": email,
            "hashed_password": hashed_password,
            "is_active": True,
            "role": role.value,
            "created_at": self._clock().isoformat(),
        }
        profile_record: dict[str, Any] = {
            "id": str(uuid4()),
            "user_id": user_record["id"],
            **profile.model_dump(include={"name", "phone", "address"}),
        }
        with self._tables() as (users, profiles):
            if users.contains(Query().email == email):
                raise DuplicateEmailError
            users.insert(user_record)
            profiles.insert(profile_record)
        return UserInDB.model_validate(user_record), Profile.model_validate(profile_record)

    def list_users(self) -> list[UserInDB]:
        with self._tables() as (users, _):
            documents = users.all()
        return [UserInDB.model_validate(document) for document in documents]

    def get_user(self, user_id: str) -> UserInDB | None:
        with self._tables() as (users, _):
            document = users.get(Query().id == user_id)
        return UserInDB.model_validate(document) if isinstance(document, Document) else None

    def get_user_by_email(self, email: str) -> UserInDB | None:
        with self._tables() as (users, _):
            document = users.get(Query().email == email)
        return UserInDB.model_validate(document) if isinstance(document, Document) else None

    def update_user(self, user_id: str, fields: dict[str, Any]) -> UserInDB | None:
        """Actualiza campos de credenciales. Comprueba el email único en la misma operación."""
        with self._tables() as (users, _):
            if not users.contains(Query().id == user_id):
                return None
            email = fields.get("email")
            if email is not None and users.contains((Query().email == email) & (Query().id != user_id)):
                raise DuplicateEmailError
            users.update(fields, Query().id == user_id)
            document = users.get(Query().id == user_id)
        assert isinstance(document, Document)
        return UserInDB.model_validate(document)

    def delete_user(self, user_id: str) -> bool:
        """Borra el usuario y su perfil vinculado (nunca queda un perfil huérfano)."""
        with self._tables() as (users, profiles):
            if not users.contains(Query().id == user_id):
                return False
            profiles.remove(Query().user_id == user_id)
            users.remove(Query().id == user_id)
        return True

    def get_profile(self, user_id: str) -> Profile | None:
        with self._tables() as (_, profiles):
            document = profiles.get(Query().user_id == user_id)
        return Profile.model_validate(document) if isinstance(document, Document) else None

    def update_profile(self, user_id: str, fields: dict[str, Any]) -> Profile | None:
        with self._tables() as (_, profiles):
            if not profiles.contains(Query().user_id == user_id):
                return None
            profiles.update(fields, Query().user_id == user_id)
            document = profiles.get(Query().user_id == user_id)
        assert isinstance(document, Document)
        return Profile.model_validate(document)

    # --- AUTH-03: tokens de restablecimiento, cambio de contraseña y auditoría ---

    def replace_reset_token(self, user_id: str, token_hash: str, expires_at: datetime) -> None:
        """Guarda un token nuevo e invalida los pendientes del mismo usuario.

        Solo el último enlace enviado sirve. De paso se borran los tokens ya
        caducados de cualquier usuario (después de `expires_at` son inútiles).
        """
        now = self._clock()
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "user_id": user_id,
            "token_hash": token_hash,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "used_at": None,
        }
        with self._db() as db:
            tokens = db.table(RESET_TOKENS_TABLE)
            tokens.remove(Query().expires_at.test(lambda value: datetime.fromisoformat(value) <= now))
            tokens.remove((Query().user_id == user_id) & Query().used_at.test(lambda value: value is None))
            tokens.insert(record)

    def consume_reset_token(self, token_hash: str, hashed_password: str) -> tuple[ResetTokenStatus, str | None]:
        """Valida el token y, si es válido, cambia la contraseña y lo marca como usado.

        Todo en la misma operación: dos peticiones con el mismo token no pueden
        pasar ambas. Devuelve el resultado y el `user_id` del token (si existe).
        """
        now = self._clock()
        with self._db() as db:
            tokens, users = db.table(RESET_TOKENS_TABLE), db.table(USERS_TABLE)
            document = tokens.get(Query().token_hash == token_hash)
            if not isinstance(document, Document):
                return ResetTokenStatus.UNKNOWN, None
            user_id = str(document["user_id"])
            if document["used_at"] is not None:
                return ResetTokenStatus.USED, user_id
            if datetime.fromisoformat(document["expires_at"]) <= now:
                return ResetTokenStatus.EXPIRED, user_id
            if not users.contains((Query().id == user_id) & (Query().is_active == True)):  # noqa: E712
                return ResetTokenStatus.UNKNOWN, user_id
            users.update({"hashed_password": hashed_password}, Query().id == user_id)
            tokens.update({"used_at": now.isoformat()}, doc_ids=[document.doc_id])
            # Cualquier otro enlace pendiente del usuario deja de valer.
            tokens.remove((Query().user_id == user_id) & Query().used_at.test(lambda value: value is None))
        return ResetTokenStatus.VALID, user_id

    def update_password(self, user_id: str, hashed_password: str) -> bool:
        """Cambia la contraseña (ya hasheada) e invalida los enlaces de restablecimiento pendientes."""
        with self._db() as db:
            users = db.table(USERS_TABLE)
            if not users.contains(Query().id == user_id):
                return False
            users.update({"hashed_password": hashed_password}, Query().id == user_id)
            db.table(RESET_TOKENS_TABLE).remove(
                (Query().user_id == user_id) & Query().used_at.test(lambda value: value is None)
            )
        return True

    def record_password_event(
        self, event: AuditEvent, user_id: str | None, ip: str | None, reason: str | None = None
    ) -> None:
        record: dict[str, Any] = {
            "id": str(uuid4()),
            "event": event.value,
            "user_id": user_id,
            "ip": ip,
            "reason": reason,
            "created_at": self._clock().isoformat(),
        }
        with self._db() as db:
            db.table(AUDIT_TABLE).insert(record)
