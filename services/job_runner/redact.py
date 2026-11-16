"""Nada sensible en un mensaje de error ni en un log (apartados A.3 y H del análisis).

`redact` quita las URL con esquema y los valores de las variables secretas del
entorno (con la contraseña de `DATABASE_URL` por separado); `describe_exception`
produce el texto que va a `error_message`: de un error de SQLAlchemy solo las
clases (su mensaje lleva SQL y datos de conexión), del resto `Clase: mensaje`
redactado y truncado. Solo librería estándar (SQLAlchemy solo para reconocer su error).
"""

import os
import re
from collections.abc import Iterable, Mapping
from urllib.parse import urlsplit

from sqlalchemy.exc import SQLAlchemyError

from .states import MAX_ERROR_MESSAGE_CHARS

REDACTED = "<redacted>"
REDACTED_URL = "<redacted-url>"
SECRET_VARIABLES = (
    "DATABASE_URL",
    "JOB_RUNNER_TEST_DATABASE_URL",
    "PIPELINE_TEST_DATABASE_URL",
    "TELEMETRY_SUPPLIER_KEY",
    "JWT_SECRET_KEY",
    "RESEND_API_KEY",
)
_MIN_SECRET_LENGTH = 4
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s'\"<>]+")


def secret_values(environ: Mapping[str, str]) -> list[str]:
    """Los valores secretos del entorno, de más largo a más corto (para no dejar restos)."""
    values: set[str] = set()
    for name in SECRET_VARIABLES:
        value = (environ.get(name) or "").strip()
        if len(value) < _MIN_SECRET_LENGTH:
            continue
        values.add(value)
        if "://" in value:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            if password and len(password) >= _MIN_SECRET_LENGTH:
                values.add(password)
    return sorted(values, key=len, reverse=True)


def redact(text: str, *, environ: Mapping[str, str] | None = None, extra: Iterable[str] = ()) -> str:
    """`text` sin valores secretos y sin URL con esquema."""
    secrets = secret_values(os.environ if environ is None else environ)
    secrets += [value for value in extra if len(value) >= _MIN_SECRET_LENGTH]
    for secret in sorted(set(secrets), key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return _URL.sub(REDACTED_URL, text)


def describe_exception(error: BaseException, *, environ: Mapping[str, str] | None = None) -> str:
    """El texto de `error_message` para una excepción: sin secretos y de ≤ `MAX_ERROR_MESSAGE_CHARS`."""
    if isinstance(error, SQLAlchemyError):
        origin = getattr(error, "orig", None)
        text = type(error).__name__ + (f" ({type(origin).__name__})" if origin is not None else "")
    else:
        message = " ".join(str(error).split())
        text = f"{type(error).__name__}: {message}" if message else type(error).__name__
        text = redact(text, environ=environ)
    return text[:MAX_ERROR_MESSAGE_CHARS]
