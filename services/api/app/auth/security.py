"""Hash de contraseñas (libpass/bcrypt) y firma de JWT (python-jose).

- Contraseñas: `passlib.hash.bcrypt` de `libpass[bcrypt]` (fork mantenido de
  passlib). Nunca se guardan ni se comparan en texto plano: solo `hash` y
  `verify`. El límite de 72 bytes se valida antes en `app/auth/models.py`.
- JWT HS256 firmado con `Settings.jwt_secret_key` (JWT_SECRET_KEY). Claims:
  `sub` = `User.id` (UUID de TinyDB), `iat` y `exp` (ahora +
  ACCESS_TOKEN_EXPIRE_MINUTES). `decode_access_token` exige firma válida,
  `sub` y `exp` no vencido; cualquier fallo → `None` (la dependencia responde 401).
- Tokens de restablecimiento (AUTH-03): cadena aleatoria de 256 bits, no un
  JWT, porque debe poder invalidarse tras usarla. En la base solo se guarda su
  SHA-256 (`hash_reset_token`); el token en claro solo viaja en el enlace del email.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import cache

from jose import JWTError, jwt
from passlib.hash import bcrypt

from app.auth.models import BCRYPT_MAX_PASSWORD_BYTES
from app.core.config import Settings

JWT_ALGORITHM = "HS256"
TOKEN_TYPE = "bearer"


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    # Una contraseña de más de 72 bytes nunca pudo registrarse: no se compara
    # (bcrypt la rechazaría o la truncaría).
    if len(password.encode("utf-8")) > BCRYPT_MAX_PASSWORD_BYTES:
        return False
    return bool(bcrypt.verify(password, hashed_password))


@cache
def _dummy_hash() -> str:
    # Valor aleatorio por proceso: no corresponde a ninguna contraseña real.
    return bcrypt.hash(secrets.token_urlsafe(32))


def burn_password_check(password: str) -> None:
    """Verificación contra un hash ficticio cuando el email no existe.

    Iguala el tiempo de respuesta del login para no revelar qué emails
    están registrados.
    """
    verify_password(password, _dummy_hash())


def new_reset_token() -> str:
    return secrets.token_urlsafe(32)


def hash_reset_token(token: str) -> str:
    # SHA-256 sin sal basta: el token tiene 256 bits aleatorios (no se puede
    # adivinar por diccionario) y así se busca por igualdad en la base.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expires_in_seconds(settings: Settings) -> int:
    assert settings.access_token_expire_minutes is not None  # lo garantiza Settings.require_auth()
    return settings.access_token_expire_minutes * 60


def create_access_token(settings: Settings, user_id: str, now: datetime | None = None) -> str:
    issued_at = now if now is not None else datetime.now(UTC)
    claims = {
        "sub": user_id,
        "iat": issued_at,
        "exp": issued_at + timedelta(seconds=expires_in_seconds(settings)),
    }
    return str(jwt.encode(claims, settings.jwt_secret_key, algorithm=JWT_ALGORITHM))


def decode_access_token(settings: Settings, token: str) -> str | None:
    """Devuelve el `sub` si el token es válido; `None` si no lo es por cualquier motivo."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require_sub": True, "require_exp": True},
        )
    except JWTError:
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) and subject else None
