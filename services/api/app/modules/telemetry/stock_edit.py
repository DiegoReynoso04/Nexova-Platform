"""Detección de `direct_stock_edit_rejected` (plan P7, definición D5).

Única excepción de D1 «A ligera»: lo emite la API, porque la interfaz no tiene
ninguna forma de intentar editar el stock. Dos casos, y solo esos:

1. `PUT`, `PATCH` o `DELETE` sobre `/inventory/products` o
   `/inventory/products/{id}` → 405, con o sin token (Starlette responde antes
   de autenticar).
2. Un `POST` de alta del inventario con `current_stock` en el body → 422
   `extra_forbidden` en `["body", "current_stock"]` (con token válido: sin él,
   la API responde antes 401).

Lo llaman los handlers de `app/core/errors.py` a través de
`app.state.stock_edit_reporter`. Nunca lanza ni cambia la respuesta: cualquier
fallo (también el de la base al buscar el activo) deja el campo en `null` o
descarta el evento. Nunca se copia el body, el `detail` ni el token. El evento
se guarda en `telemetry_events` con `service='api'` y, antes, sale al log (D8).
`product_category` y `programme_id` van en `null` hasta P1.
"""

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import Request
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.auth.security import read_token_claims
from app.core.config import Settings
from app.modules.inventory.models import Asset
from app.modules.inventory.vocabulary import QUANTITY_MAX, Office
from app.modules.telemetry.collector import store_api_event
from app.modules.telemetry.emitter import Throttle, emit, office_currency, office_label

EVENT_TYPE = "direct_stock_edit_rejected"
WRITE_METHODS = frozenset({"PUT", "PATCH", "DELETE"})
PRODUCTS_PATH = "/inventory/products"
# Altas del inventario en las que un `current_stock` en el body es un intento (caso 2).
CREATE_PATHS = frozenset({PRODUCTS_PATH, "/inventory/orders/inbound", "/inventory/orders/outbound"})
STOCK_FIELD_LOC = ("body", "current_stock")
INT4_MAX = QUANTITY_MAX
OFFICE_VALUES = frozenset(office.value for office in Office)


def _product_route(path: str) -> tuple[str, str | None] | None:
    """`(plantilla, segmento del id)` si el path es la colección o un activo; si no, `None`."""
    trimmed = path[:-1] if path.endswith("/") and path != "/" else path
    if trimmed == PRODUCTS_PATH:
        return PRODUCTS_PATH, None
    prefix = f"{PRODUCTS_PATH}/"
    segment = trimmed[len(prefix) :] if trimmed.startswith(prefix) else ""
    if segment and "/" not in segment:
        return f"{PRODUCTS_PATH}/{{id}}", segment
    return None


def _asset_id(segment: str | None) -> int | None:
    if segment is None or not segment.isascii() or not segment.isdigit():
        return None
    value = int(segment)
    return value if 1 <= value <= INT4_MAX else None


def _strict_int(value: object) -> int | None:
    """Un entero JSON de 1 a int4 (nunca un bool ni un texto)."""
    return value if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= INT4_MAX else None


class StockEditReporter:
    def __init__(self, settings: Settings, engine: Engine, throttle: Throttle | None = None) -> None:
        self.settings = settings
        self.engine = engine
        self.throttle = throttle or Throttle()

    def method_not_allowed(self, request: Request) -> None:
        """Caso 1: lo llama el handler del 405."""
        try:
            if request.method not in WRITE_METHODS:
                return
            route = _product_route(request.url.path)
            if route is None:
                return
            template, segment = route
            self._emit(request, "method_not_allowed", template, 405, _asset_id(segment), None, None)
        except Exception:  # noqa: BLE001 — la telemetría nunca cambia la respuesta
            return

    def validation_failed(self, request: Request, errors: Sequence[Mapping[str, Any]], body: object) -> bool:
        """Caso 2: lo llama el handler del 422. `True` si era un intento de editar el stock."""
        try:
            if request.method != "POST" or request.url.path not in CREATE_PATHS:
                return False
            attempt = next(
                (error for error in errors if error.get("type") == "extra_forbidden" and tuple(error.get("loc", ())) == STOCK_FIELD_LOC),
                None,
            )
            if attempt is None:
                return False
            fields = body if isinstance(body, Mapping) else {}
            asset_id = _strict_int(fields.get("asset_id"))
            office = fields.get("office") if request.url.path == PRODUCTS_PATH else None
            body_office = Office(office) if isinstance(office, str) and office in OFFICE_VALUES else None
            self._emit(request, "stock_field_in_body", request.url.path, 422, asset_id, _strict_int(attempt.get("input")), body_office)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _office_of(self, asset_id: int | None) -> Office | None:
        if asset_id is None:
            return None
        try:
            with Session(self.engine) as session:
                asset = session.get(Asset, asset_id)
                return Office(asset.office) if asset is not None else None
        except Exception:  # noqa: BLE001 — base caída: el evento sale con la oficina en null
            return None

    def _emit(
        self,
        request: Request,
        attempt_kind: str,
        template: str,
        status_code: int,
        product_id: int | None,
        quantity: int | None,
        fallback_office: Office | None,
    ) -> None:
        claims = None
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            claims = read_token_claims(self.settings, token.strip())
        user_id = claims.sub if claims is not None else None
        suppressed = self.throttle.admit((user_id or "anonymous", template, request.method))
        if suppressed is None:
            return
        office = self._office_of(product_id) or fallback_office
        emit(
            EVENT_TYPE,
            {
                "office": office_label(office) if office is not None else None,
                "product_id": product_id,
                "product_category": None,
                "programme_id": None,
                "quantity": quantity,
                "currency": office_currency(office).value if office is not None else None,
                "attempt_kind": attempt_kind,
                "http_method": request.method,
                "route_template": template,
                "status_code": status_code,
                "authenticated": claims is not None,
                "suppressed_count": suppressed,
            },
            user_id=user_id,
            session_id=claims.sid if claims is not None else None,
            sink=lambda event: store_api_event(self.engine, event),
        )
