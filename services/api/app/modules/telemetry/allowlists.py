"""Allowlist de cada evento que se guarda, para la API (ticket de almacenamiento).

Copia de `docs/telemetry/event-schemas.json` (sin las `description`): la imagen
de la API se construye solo con `services/`, así que el JSON no está en el
contenedor. `tests/test_telemetry_storage.py` compara esta copia con el JSON: un
cambio en el plan que no llegue aquí hace fallar la suite.

Solo los 15 eventos que llegan a la tabla: los 14 de emisor frontend y
`direct_stock_edit_rejected` (D8). Los de los otros 37 aún no se emiten, y su
vocabulario choca además con el del gestor de incidencias, que la API no puede
repetir (`tests/test_architecture.py`).
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventAllowlist:
    """`properties`: clave → esquema JSON de su valor; todas son obligatorias (plan §6).

    `identity_required`: `userId` y `sessionId` no pueden ser `null` (plan §5.1).
    `office_currency`: pares válidos de oficina y moneda; vacío si el evento no los lleva.
    """

    properties: Mapping[str, Mapping[str, object]]
    identity_required: bool = False
    office_currency: tuple[tuple[str | None, str | None], ...] = ()


EVENT_ALLOWLISTS: Mapping[str, EventAllowlist] = {
    "inbound_order_created": EventAllowlist(
        properties={
            "office": {"enum": ["valencia", "miami"]},
            "product_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "product_category": {"enum": ["training_kit", "certification", "onboarding_equipment", None]},
            "programme_id": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "currency": {"enum": ["EUR", "USD"]},
            "inbound_order_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "unit_cost": {"type": "number", "exclusiveMinimum": 0, "maximum": 9999999999.99},
            "supplier_key": {"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64},
            "asset_category": {"enum": ["hardware", "peripherals", "office_supplies", "training_materials"]},
        },
        identity_required=True,
        office_currency=(("valencia", "EUR"), ("miami", "USD")),
    ),
    "outbound_order_created": EventAllowlist(
        properties={
            "office": {"enum": ["valencia", "miami"]},
            "product_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "product_category": {"enum": ["training_kit", "certification", "onboarding_equipment", None]},
            "programme_id": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "currency": {"enum": ["EUR", "USD"]},
            "outbound_order_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "exit_type": {"enum": ["allocation", "consumption"]},
            "stock_after": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "asset_category": {"enum": ["hardware", "peripherals", "office_supplies", "training_materials"]},
        },
        identity_required=True,
        office_currency=(("valencia", "EUR"), ("miami", "USD")),
    ),
    "stock_threshold_triggered": EventAllowlist(
        properties={
            "office": {"enum": ["valencia", "miami"]},
            "product_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "product_category": {"enum": ["training_kit", "certification", "onboarding_equipment", None]},
            "programme_id": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "currency": {"enum": ["EUR", "USD"]},
            "outbound_order_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "stock_before": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "stock_after": {"type": "integer", "minimum": 0, "maximum": 2147483647},
            "min_stock": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "asset_category": {"enum": ["hardware", "peripherals", "office_supplies", "training_materials"]},
        },
        identity_required=True,
        office_currency=(("valencia", "EUR"), ("miami", "USD")),
    ),
    "direct_stock_edit_rejected": EventAllowlist(
        properties={
            "office": {"enum": ["valencia", "miami", None]},
            "product_id": {"type": ["integer", "null"], "minimum": 1, "maximum": 2147483647},
            "product_category": {"enum": ["training_kit", "certification", "onboarding_equipment", None]},
            "programme_id": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64},
            "quantity": {"type": ["integer", "null"], "minimum": 1, "maximum": 2147483647},
            "currency": {"enum": ["EUR", "USD", None]},
            "attempt_kind": {"enum": ["method_not_allowed", "stock_field_in_body"]},
            "http_method": {"enum": ["PUT", "PATCH", "DELETE", "POST"]},
            "route_template": {"enum": ["/inventory/products", "/inventory/products/{id}", "/inventory/orders/inbound", "/inventory/orders/outbound"]},
            "status_code": {"enum": [405, 422]},
            "authenticated": {"type": "boolean"},
            "suppressed_count": {"type": "integer", "minimum": 0},
        },
        office_currency=(("valencia", "EUR"), ("miami", "USD"), (None, None)),
    ),
    "kit_cost_variance_detected": EventAllowlist(
        properties={
            "office": {"enum": ["valencia", "miami"]},
            "product_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "product_category": {"enum": ["training_kit", "certification", "onboarding_equipment", None]},
            "programme_id": {"type": ["string", "null"], "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 64},
            "quantity": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "currency": {"enum": ["EUR", "USD"]},
            "inbound_order_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
            "supplier_key": {"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64},
            "unit_cost": {"type": "number", "exclusiveMinimum": 0, "maximum": 9999999999.99},
            "reference_unit_cost": {"type": "number", "exclusiveMinimum": 0, "maximum": 9999999999.99},
            "variance_pct": {"type": "number", "minimum": -100, "maximum": 1000000},
            "direction": {"enum": ["increase", "decrease"]},
            "threshold_pct": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000},
            "reference_window": {"type": "integer", "minimum": 1, "maximum": 100},
            "asset_category": {"enum": ["hardware", "peripherals", "office_supplies", "training_materials"]},
        },
        identity_required=True,
        office_currency=(("valencia", "EUR"), ("miami", "USD")),
    ),
    "user_logged_out": EventAllowlist(
        properties={
            "trigger": {"enum": ["header_button", "session_error_screen"]},
        },
        identity_required=True,
    ),
    "page_viewed": EventAllowlist(
        properties={
            "route_template": {"enum": ["/", "/login", "/register", "/forgot-password", "/reset-password", "/account/profile", "/account/change-password", "/incidents", "/suppliers", "/incident-manager", "/incident-manager/new", "/inventory/products", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders"]},
            "previous_route_template": {"enum": ["/", "/login", "/register", "/forgot-password", "/reset-password", "/account/profile", "/account/change-password", "/incidents", "/suppliers", "/incident-manager", "/incident-manager/new", "/inventory/products", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders", None]},
            "entry": {"enum": ["initial_load", "in_app_navigation"]},
        },
    ),
    "page_not_found_viewed": EventAllowlist(
        properties={
            "previous_route_template": {"enum": ["/", "/login", "/register", "/forgot-password", "/reset-password", "/account/profile", "/account/change-password", "/incidents", "/suppliers", "/incident-manager", "/incident-manager/new", "/inventory/products", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders", None]},
        },
    ),
    "form_started": EventAllowlist(
        properties={
            "form": {"enum": ["login", "register", "forgot_password", "reset_password", "change_password", "profile", "supplier_create", "incident_create", "incident_analysis_upload", "inbound_order", "outbound_order"]},
        },
    ),
    "form_submitted": EventAllowlist(
        properties={
            "form": {"enum": ["login", "register", "forgot_password", "reset_password", "change_password", "profile", "supplier_create", "incident_create", "incident_analysis_upload", "inbound_order", "outbound_order"]},
            "outcome": {"enum": ["success", "validation_error", "api_rejected", "session_expired", "network_error", "server_error"]},
            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 86400000},
            "attempt_number": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
    ),
    "form_abandoned": EventAllowlist(
        properties={
            "form": {"enum": ["login", "register", "forgot_password", "reset_password", "change_password", "profile", "supplier_create", "incident_create", "incident_analysis_upload", "inbound_order", "outbound_order"]},
            "last_field": {"type": ["string", "null"], "pattern": "^[a-z_]+$", "maxLength": 40},
            "had_validation_error": {"type": "boolean"},
            "had_api_error": {"type": "boolean"},
            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 86400000},
        },
    ),
    "form_validation_failed": EventAllowlist(
        properties={
            "form": {"enum": ["login", "register", "forgot_password", "reset_password", "change_password", "profile", "supplier_create", "incident_create", "incident_analysis_upload", "inbound_order", "outbound_order"]},
            "fields": {"type": "array", "items": {"type": "string", "pattern": "^[a-z_]+$", "maxLength": 40}, "maxItems": 20, "uniqueItems": True},
        },
    ),
    "frontend_error_captured": EventAllowlist(
        properties={
            "boundary": {"enum": ["route", "global"]},
            "route_template": {"enum": ["/", "/login", "/register", "/forgot-password", "/reset-password", "/account/profile", "/account/change-password", "/incidents", "/suppliers", "/incident-manager", "/incident-manager/new", "/inventory/products", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders", None]},
            "suppressed_count": {"type": "integer", "minimum": 0},
        },
    ),
    "client_request_failed": EventAllowlist(
        properties={
            "kind": {"enum": ["network", "timeout", "config"]},
            "http_method": {"enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
            "api_route_template": {"enum": ["/auth/login", "/auth/me", "/auth/forgot-password", "/auth/reset-password", "/auth/change-password", "/users", "/users/{user_id}", "/profiles/me", "/suppliers", "/suppliers/{supplier_id}", "/suppliers/{supplier_id}/rate", "/suppliers/{supplier_id}/status", "/api/incidents/analyze", "/api/incidents/results/export", "/api/incidents", "/api/incidents/summary", "/api/incidents/{incident_id}", "/api/incidents/{incident_id}/status", "/inventory/products", "/inventory/products/{id}", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders", "/telemetry/events"]},
            "timeout_ms": {"type": ["integer", "null"], "minimum": 1},
            "suppressed_count": {"type": "integer", "minimum": 0},
        },
    ),
    "page_load_recorded": EventAllowlist(
        properties={
            "route_template": {"enum": ["/suppliers", "/incident-manager", "/inventory/products", "/inventory/orders"]},
            "duration_ms": {"type": "integer", "minimum": 0, "maximum": 120000},
            "outcome": {"enum": ["data", "empty", "error"]},
        },
    ),
}
