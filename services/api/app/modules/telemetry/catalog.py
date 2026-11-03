"""Catálogo de eventos del plan de telemetría, para la API.

Copia de `docs/telemetry/event-schemas.json` (versión y `event_type` de cada
evento, en el orden del plan): la imagen de la API se construye solo con
`services/`, así que el JSON no está en el contenedor y no se puede leer en
tiempo de ejecución. `tests/test_telemetry_events.py` compara esta copia con el
JSON: un cambio en el plan que no llegue aquí hace fallar la suite.
"""

# Versión de los esquemas (plan §5.4). Es global: la misma en todos los eventos.
SCHEMA_VERSION = "1.0.0"

# Los 52 eventos del catálogo (plan §4), en el mismo orden.
EVENT_TYPES = (
    "inbound_order_created",
    "outbound_order_created",
    "stock_threshold_triggered",
    "direct_stock_edit_rejected",
    "kit_cost_variance_detected",
    "product_created",
    "inbound_order_rejected",
    "outbound_order_rejected",
    "inventory_validation_failed",
    "user_logged_in",
    "login_failed",
    "user_registered",
    "registration_failed",
    "session_expired",
    "auth_token_rejected",
    "user_logged_out",
    "password_reset_requested",
    "password_reset_completed",
    "password_reset_rejected",
    "password_changed",
    "password_change_rejected",
    "password_reset_email_failed",
    "access_denied",
    "user_role_changed",
    "user_deleted",
    "page_viewed",
    "page_not_found_viewed",
    "form_started",
    "form_submitted",
    "form_abandoned",
    "form_validation_failed",
    "frontend_error_captured",
    "client_request_failed",
    "server_error_returned",
    "storage_unavailable_detected",
    "api_startup_failed",
    "cache_lookup_recorded",
    "api_latency_recorded",
    "page_load_recorded",
    "supplier_created",
    "supplier_rate_updated",
    "supplier_status_changed",
    "supplier_deleted",
    "supplier_list_filtered",
    "incident_created",
    "incident_status_changed",
    "incident_status_change_rejected",
    "incident_validation_failed",
    "incident_list_filtered",
    "incident_analysis_completed",
    "incident_analysis_rejected",
    "incident_results_exported",
)
