"""Formato de error único `{"detail": str, "code": str}` y su traducción.

Ninguna respuesta de error incluye datos enviados por el cliente: el CSV puede
contener emails reales (ver docs/COMPANY_INCIDENT_FILE_ANALIZER_PROJECT.md).
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("nexova.api")

INTERNAL_ERROR_DETAIL = "internal server error"
# Campos de los errores de validación que se devuelven. Se descartan `input`,
# `ctx` y `url`: `input` reproduce el valor recibido (p. ej. un CSV pegado
# como texto) y `ctx` puede contener partes de él.
_VALIDATION_ERROR_KEYS = ("loc", "msg", "type")


class ApiError(HTTPException):
    """Error de la API con código estable. `detail` nunca contiene datos del archivo.

    Hereda de `fastapi.HTTPException` porque FastAPI solo deja propagar esa
    clase si se lanza mientras lee el body; cualquier otra la convierte en 400.
    """

    code: str = "error"

    def __init__(
        self, status_code: int, code: str, detail: str, headers: Mapping[str, str] | None = None
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=dict(headers) if headers else None)
        self.code = code


class InvalidCsvError(ApiError):
    def __init__(self, detail: str) -> None:
        super().__init__(400, "invalid_csv", detail)


class NoAnalysisError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "no_analysis", "no analysis available yet")


class SupplierNotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "supplier_not_found", "supplier not found")


# AUTH-01. Los mensajes son fijos: nunca repiten el email, el token ni la
# contraseña recibidos. RFC 6750: un 401 de un recurso Bearer lleva
# `WWW-Authenticate: Bearer`.
_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}


class NotAuthenticatedError(ApiError):
    """Sin token, token mal formado, firma inválida, expirado o usuario inexistente."""

    def __init__(self) -> None:
        super().__init__(401, "not_authenticated", "could not validate credentials", _BEARER_CHALLENGE)


class InvalidCredentialsError(ApiError):
    """Login fallido. El mismo mensaje si el email no existe o la contraseña no coincide."""

    def __init__(self) -> None:
        super().__init__(401, "invalid_credentials", "incorrect email or password", _BEARER_CHALLENGE)


class ForbiddenError(ApiError):
    """Autenticado, pero sin permiso sobre el recurso (otro usuario, rol reservado a admin)."""

    def __init__(self, detail: str = "not allowed to access this resource") -> None:
        super().__init__(403, "forbidden", detail)


class UserNotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "user_not_found", "user not found")


class ProfileNotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "profile_not_found", "profile not found")


class EmailAlreadyRegisteredError(ApiError):
    def __init__(self) -> None:
        super().__init__(409, "email_already_registered", "email already registered")


# AUTH-03. Mismo criterio: mensajes fijos, nunca el token ni las contraseñas.
class InvalidResetTokenError(ApiError):
    """Token de restablecimiento desconocido, expirado o ya usado: un solo código para los tres casos."""

    def __init__(self) -> None:
        super().__init__(400, "invalid_reset_token", "reset token is invalid, expired or already used")


class IncorrectPasswordError(ApiError):
    """`POST /auth/change-password` con una contraseña actual que no coincide.

    400 y no 401: la sesión es válida; un 401 haría que el frontend la cerrase.
    """

    def __init__(self) -> None:
        super().__init__(400, "incorrect_password", "current password is incorrect")


# Gestor centralizado de incidencias. A diferencia del resto de la API (422),
# su validación responde 400 con un error por campo `{field, error, message}`
# (exigencia del enunciado del proyecto; SPECS Parte E). Los mensajes vienen de
# nexova_shared y nunca repiten el valor recibido.
FieldErrorDetail = dict[str, str]


class IncidentFieldsError(ApiError):
    def __init__(self, errors: list[FieldErrorDetail]) -> None:
        super().__init__(400, "validation_error", "")
        self.detail = errors


class InvalidStatusTransitionApiError(ApiError):
    def __init__(self, errors: list[FieldErrorDetail]) -> None:
        super().__init__(400, "invalid_status_transition", "")
        self.detail = errors


class IncidentNotFoundError(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "incident_not_found", "incident not found")


class FileTooLargeError(ApiError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(413, "file_too_large", f"request body exceeds the {max_bytes} bytes limit")


class UnsupportedFileTypeError(ApiError):
    def __init__(self) -> None:
        super().__init__(415, "unsupported_file_type", "only .csv files are accepted")


class StorageUnavailableError(ApiError):
    """Un archivo TinyDB no se puede abrir, leer o escribir, o no es una base válida.

    503 y no 500: el fallo es del almacenamiento, no del código. El mensaje es
    fijo: nunca la ruta del archivo ni el mensaje de la excepción original
    (un `JSONDecodeError` guarda el contenido entero del archivo en `.doc`).
    """

    def __init__(self) -> None:
        super().__init__(503, "storage_unavailable", "storage is temporarily unavailable")


def error_response(
    status_code: int, code: str, detail: object, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail, "code": code}, headers=headers)


async def _http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    # Las cabeceras de la excepción se conservan (p. ej. `Allow` en un 405,
    # obligatoria según RFC 9110).
    if isinstance(exc, ApiError):
        return error_response(exc.status_code, exc.code, exc.detail, exc.headers)
    # Errores de Starlette/FastAPI (404 de ruta, 405, multipart ilegible...):
    # se responde con la frase estándar del código, no con `exc.detail`.
    status = HTTPStatus(exc.status_code)
    code = status.phrase.lower().replace(" ", "_").replace("-", "_")
    return error_response(status.value, code, status.phrase, exc.headers)


async def _validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [{key: error[key] for key in _VALIDATION_ERROR_KEYS if key in error} for error in exc.errors()]
    return error_response(422, "validation_error", errors)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)


class InternalErrorMiddleware:
    """Convierte cualquier excepción no controlada en un 500 opaco.

    Es un middleware y no un `exception_handler(Exception)` porque Starlette,
    tras ejecutar ese handler, relanza la excepción y el servidor registra la
    traza con su mensaje, que podría contener datos del archivo. Aquí solo se
    registra el nombre de la clase.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:  # noqa: BLE001 — frontera final del proceso
            logger.error("unhandled error while processing request: %s", type(exc).__name__)
            if not response_started:
                response = error_response(500, "internal_error", INTERNAL_ERROR_DETAIL)
                await response(scope, receive, send)


def log_email_delivery_failure(exc: Exception) -> None:
    """Fallo al enviar el email de restablecimiento (AUTH-03).

    Se envía en segundo plano, después de responder, así que el cliente nunca
    lo ve. Como en el 500, solo se registra el nombre de la clase: ni el email
    del destinatario ni el enlace con el token.
    """
    logger.error("password reset email could not be delivered: %s", type(exc).__name__)


def log_storage_failure(store: str, exc: BaseException) -> None:
    """Fallo de un archivo TinyDB (`app/core/storage.py`).

    Solo el nombre del almacén (`suppliers`, `auth`, `incidents`) y el de la
    clase de la excepción: ni la ruta del archivo ni el mensaje, que en un
    `JSONDecodeError` puede citar el contenido y en un `OSError`, la ruta.
    """
    logger.error("storage %s is unavailable: %s", store, type(exc).__name__)
