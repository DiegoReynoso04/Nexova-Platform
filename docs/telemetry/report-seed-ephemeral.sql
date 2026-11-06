-- Fictitious events for GET /telemetry/report. EPHEMERAL DATABASE ONLY, never the demo:
-- telemetry_events is immutable, so these rows could not be removed.
-- Guide: docs/telemetry/report-review.md. Run it once, as the test role.
-- ASCII on purpose: PowerShell 5.1 pipes it with the console encoding.
--
-- Days are relative to today (UTC): D-9 is outside the default 7-day window, D-3 is
-- left empty on purpose (events_per_day must show it at 0). All values come from the
-- allowlists of docs/telemetry/event-schemas.json.

\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
  IF current_database() <> 'nexova_test' THEN
    RAISE EXCEPTION 'This seed only runs on nexova_test, not on %', current_database();
  END IF;
END
$$;

CREATE TEMP TABLE seed_clock ON COMMIT DROP AS
SELECT date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS today;

-- Fixed id: a second run fails here and rolls everything back.
INSERT INTO telemetry_events (event_id, event_type, timestamp, service, schema_version, tags)
SELECT '00000000-0000-4000-8000-000000000001', 'page_viewed', today - interval '9 days' + interval '12 hours', 'backoffice', '1.0.0',
       '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}'::jsonb
FROM seed_clock;

INSERT INTO telemetry_events (event_id, event_type, timestamp, service, schema_version, tags)
SELECT gen_random_uuid(), v.event_type, today - make_interval(days => v.ago) + v.at::interval + (g - 1) * interval '1 second', v.service, '1.0.0', v.tags::jsonb
FROM seed_clock,
     (VALUES
       -- D-4: logins that fail, latency with an error, a throttled network failure.
       (4, '00:00:00', 'page_viewed', 'backoffice', 1, '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}'),
       (4, '09:00:00', 'page_viewed', 'backoffice', 9, '{"route_template": "/suppliers", "previous_route_template": "/", "entry": "in_app_navigation"}'),
       (4, '09:10:00', 'form_started', 'backoffice', 2, '{"form": "login"}'),
       (4, '09:11:00', 'form_submitted', 'backoffice', 3, '{"form": "login", "outcome": "api_rejected", "duration_ms": 4000, "attempt_number": 1}'),
       (4, '09:12:00', 'form_submitted', 'backoffice', 1, '{"form": "login", "outcome": "success", "duration_ms": 6000, "attempt_number": 2}'),
       (4, '09:20:00', 'page_load_recorded', 'backoffice', 1, '{"route_template": "/suppliers", "duration_ms": 100, "outcome": "data"}'),
       (4, '09:21:00', 'page_load_recorded', 'backoffice', 1, '{"route_template": "/suppliers", "duration_ms": 300, "outcome": "data"}'),
       (4, '09:22:00', 'page_load_recorded', 'backoffice', 1, '{"route_template": "/suppliers", "duration_ms": 5000, "outcome": "error"}'),
       (4, '09:30:00', 'client_request_failed', 'backoffice', 1, '{"kind": "network", "http_method": "GET", "api_route_template": "/suppliers", "timeout_ms": null, "suppressed_count": 4}'),
       -- D-2: every other error type, the API emitter and a form that is abandoned.
       (2, '10:00:00', 'page_viewed', 'backoffice', 5, '{"route_template": "/inventory/products", "previous_route_template": "/", "entry": "in_app_navigation"}'),
       (2, '10:10:00', 'page_load_recorded', 'backoffice', 1, '{"route_template": "/inventory/products", "duration_ms": 400, "outcome": "data"}'),
       (2, '10:11:00', 'page_load_recorded', 'backoffice', 1, '{"route_template": "/inventory/orders", "duration_ms": 50, "outcome": "empty"}'),
       (2, '10:20:00', 'form_submitted', 'backoffice', 1, '{"form": "login", "outcome": "network_error", "duration_ms": 3000, "attempt_number": 1}'),
       (2, '10:21:00', 'form_submitted', 'backoffice', 1, '{"form": "login", "outcome": "server_error", "duration_ms": 3000, "attempt_number": 2}'),
       (2, '10:22:00', 'form_submitted', 'backoffice', 1, '{"form": "login", "outcome": "validation_error", "duration_ms": 3000, "attempt_number": 3}'),
       (2, '10:23:00', 'form_submitted', 'backoffice', 1, '{"form": "inbound_order", "outcome": "session_expired", "duration_ms": 9000, "attempt_number": 1}'),
       (2, '10:24:00', 'form_submitted', 'backoffice', 1, '{"form": "inbound_order", "outcome": "api_rejected", "duration_ms": 9000, "attempt_number": 2}'),
       (2, '10:25:00', 'form_submitted', 'backoffice', 1, '{"form": "inbound_order", "outcome": "success", "duration_ms": 9000, "attempt_number": 3}'),
       (2, '10:30:00', 'form_validation_failed', 'backoffice', 1, '{"form": "supplier_create", "fields": ["name"]}'),
       (2, '10:31:00', 'form_abandoned', 'backoffice', 1, '{"form": "supplier_create", "last_field": "name", "had_validation_error": true, "had_api_error": false, "duration_ms": 12000}'),
       (2, '10:40:00', 'page_not_found_viewed', 'backoffice', 1, '{"previous_route_template": "/suppliers"}'),
       (2, '10:41:00', 'frontend_error_captured', 'backoffice', 1, '{"boundary": "route", "route_template": "/suppliers", "suppressed_count": 1}'),
       (2, '10:50:00', 'direct_stock_edit_rejected', 'api', 1, '{"office": null, "product_id": null, "product_category": null, "programme_id": null, "quantity": null, "currency": null, "attempt_kind": "method_not_allowed", "http_method": "PUT", "route_template": "/inventory/products", "status_code": 405, "authenticated": false, "suppressed_count": 2}'),
       (2, '10:55:00', 'user_logged_out', 'backoffice', 1, '{"trigger": "header_button"}'),
       -- D-1: the four business events, which must stay out of the rates and tags.
       (1, '00:00:00', 'page_viewed', 'backoffice', 1, '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}'),
       (1, '11:00:00', 'page_viewed', 'backoffice', 1, '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}'),
       (1, '11:10:00', 'form_submitted', 'backoffice', 1, '{"form": "login", "outcome": "api_rejected", "duration_ms": 2000, "attempt_number": 1}'),
       (1, '11:11:00', 'form_submitted', 'backoffice', 2, '{"form": "login", "outcome": "success", "duration_ms": 2000, "attempt_number": 2}'),
       (1, '11:20:00', 'inbound_order_created', 'backoffice', 1, '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 5, "currency": "EUR", "inbound_order_id": 1, "unit_cost": 10.5, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "hardware"}'),
       (1, '11:21:00', 'outbound_order_created', 'backoffice', 1, '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 2, "currency": "EUR", "outbound_order_id": 1, "exit_type": "consumption", "stock_after": 3, "asset_category": "hardware"}'),
       (1, '11:22:00', 'stock_threshold_triggered', 'backoffice', 1, '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 2, "currency": "EUR", "outbound_order_id": 1, "stock_before": 5, "stock_after": 3, "min_stock": 5, "asset_category": "hardware"}'),
       (1, '11:23:00', 'kit_cost_variance_detected', 'backoffice', 1, '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 5, "currency": "EUR", "inbound_order_id": 1, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "unit_cost": 12.5, "reference_unit_cost": 10.0, "variance_pct": 25.0, "direction": "increase", "threshold_pct": 10.0, "reference_window": 3, "asset_category": "hardware"}'),
       -- D-0: the first second of today, so the default window ends with a row.
       (0, '00:00:01', 'page_viewed', 'backoffice', 1, '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}')
     ) AS v(ago, at, event_type, service, n, tags),
     generate_series(1, v.n) AS g;

COMMIT;

SELECT count(*) AS seeded FROM telemetry_events;
