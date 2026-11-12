-- Fictitious source data for the business performance pipeline. EPHEMERAL DATABASE ONLY,
-- never the demo: telemetry_events is immutable, so these rows could not be removed.
-- Guide: docs/reporting/implementation-review.md (stop 2). Run it once, as the test role,
-- after telemetry_events and the inventory tables exist.
-- ASCII on purpose: PowerShell 5.1 pipes it with the console encoding.
--
-- No real programme, order, supplier or person: programme_id is null in every event
-- (P1 is pending), order ids are made up, supplier_key is all zeros. Tag values follow
-- the allowlists of docs/telemetry/event-schemas.json.
--
-- Weeks (Monday, UTC):
--   2026-10-19  both offices; two inbound with decimal costs; a shortage in Miami;
--               technical events.
--   2026-10-26  a cost variance in Valencia; the same inbound order with two eventIds;
--               the same Miami outbound order with two eventIds; a Miami event on Sunday
--               at 23:59 UTC (still this week); one inventory entry and exit (reconciliation).
--   2026-11-02  a Valencia event at Monday 00:00:00 UTC (this week, not the previous one);
--               a duplicated Valencia outbound order; a Miami inbound.
--   2026-11-09  one Valencia outbound (current week on 2026-11-10: not in the default run).

\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
  IF current_database() <> 'nexova_test' THEN
    RAISE EXCEPTION 'This seed only runs on nexova_test, not on %', current_database();
  END IF;
END
$$;

-- Fixed ids: a second run fails on the primary key and rolls everything back.
INSERT INTO telemetry_events (event_id, event_type, timestamp, service, schema_version, tags)
SELECT v.event_id::uuid, v.event_type, v.ts::timestamptz, 'backoffice', '1.0.0', v.tags::jsonb
FROM (VALUES
  -- 2026-10-19
  ('00000000-0000-4000-9000-000000000101', 'inbound_order_created', '2026-10-20 09:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 10, "currency": "EUR", "inbound_order_id": 101, "unit_cost": 12.50, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000102', 'inbound_order_created', '2026-10-21 10:30:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 3, "currency": "EUR", "inbound_order_id": 102, "unit_cost": 7.35, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000103', 'outbound_order_created', '2026-10-21 11:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 2, "currency": "EUR", "outbound_order_id": 201, "exit_type": "consumption", "stock_after": 11, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000104', 'outbound_order_created', '2026-10-22 15:00:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 1, "currency": "USD", "outbound_order_id": 301, "exit_type": "allocation", "stock_after": 6, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000105', 'outbound_order_created', '2026-10-23 16:00:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 2, "currency": "USD", "outbound_order_id": 302, "exit_type": "consumption", "stock_after": 4, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000106', 'stock_threshold_triggered', '2026-10-23 16:00:01+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 2, "currency": "USD", "outbound_order_id": 302, "stock_before": 6, "stock_after": 4, "min_stock": 5, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000107', 'page_viewed', '2026-10-20 08:00:00+00',
   '{"route_template": "/", "previous_route_template": null, "entry": "initial_load"}'),
  ('00000000-0000-4000-9000-000000000108', 'page_viewed', '2026-10-20 08:01:00+00',
   '{"route_template": "/inventory/products", "previous_route_template": "/", "entry": "in_app_navigation"}'),
  -- 2026-10-26
  ('00000000-0000-4000-9000-000000000201', 'inbound_order_created', '2026-10-27 09:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 4, "currency": "EUR", "inbound_order_id": 103, "unit_cost": 15.00, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000202', 'inbound_order_created', '2026-10-27 09:02:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 4, "currency": "EUR", "inbound_order_id": 103, "unit_cost": 15.00, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000203', 'kit_cost_variance_detected', '2026-10-27 09:00:01+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 4, "currency": "EUR", "inbound_order_id": 103, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "unit_cost": 15.00, "reference_unit_cost": 11.28, "variance_pct": 32.98, "direction": "increase", "threshold_pct": 10.0, "reference_window": 3, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000204', 'inbound_order_created', '2026-10-28 14:00:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 5, "currency": "USD", "inbound_order_id": 401, "unit_cost": 9.99, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000205', 'outbound_order_created', '2026-10-29 10:00:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 1, "currency": "USD", "outbound_order_id": 303, "exit_type": "allocation", "stock_after": 8, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000206', 'outbound_order_created', '2026-10-29 10:00:30+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 1, "currency": "USD", "outbound_order_id": 303, "exit_type": "allocation", "stock_after": 8, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000207', 'outbound_order_created', '2026-11-01 23:59:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 1, "currency": "USD", "outbound_order_id": 304, "exit_type": "consumption", "stock_after": 7, "asset_category": "hardware"}'),
  ('00000000-0000-4000-9000-000000000208', 'outbound_order_created', '2026-10-30 12:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 9, "currency": "EUR", "outbound_order_id": 202, "exit_type": "consumption", "stock_after": 3, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000209', 'stock_threshold_triggered', '2026-10-30 12:00:01+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 9, "currency": "EUR", "outbound_order_id": 202, "stock_before": 12, "stock_after": 3, "min_stock": 5, "asset_category": "training_materials"}'),
  -- 2026-11-02
  ('00000000-0000-4000-9000-000000000301', 'outbound_order_created', '2026-11-02 00:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 1, "currency": "EUR", "outbound_order_id": 203, "exit_type": "consumption", "stock_after": 2, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000302', 'outbound_order_created', '2026-11-04 09:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 1, "currency": "EUR", "outbound_order_id": 204, "exit_type": "allocation", "stock_after": 1, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000303', 'outbound_order_created', '2026-11-04 09:00:05+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 1, "currency": "EUR", "outbound_order_id": 204, "exit_type": "allocation", "stock_after": 1, "asset_category": "training_materials"}'),
  ('00000000-0000-4000-9000-000000000304', 'inbound_order_created', '2026-11-05 13:00:00+00',
   '{"office": "miami", "product_id": 2, "product_category": null, "programme_id": null, "quantity": 2, "currency": "USD", "inbound_order_id": 402, "unit_cost": 20.10, "supplier_key": "0000000000000000000000000000000000000000000000000000000000000000", "asset_category": "hardware"}'),
  -- 2026-11-09 (current week on 2026-11-10)
  ('00000000-0000-4000-9000-000000000401', 'outbound_order_created', '2026-11-10 08:00:00+00',
   '{"office": "valencia", "product_id": 1, "product_category": null, "programme_id": null, "quantity": 1, "currency": "EUR", "outbound_order_id": 205, "exit_type": "consumption", "stock_after": 0, "asset_category": "training_materials"}')
) AS v(event_id, event_type, ts, tags);

-- Inventory rows for the reconciliation only (they never change a KPI): week 2026-10-26.
INSERT INTO assets (id, name, sku, category, office)
VALUES (9001, 'Fictitious asset', 'FAKE-SKU-9001', 'training_materials', 'Valencia');
INSERT INTO asset_entries (asset_id, quantity, supplier, office, created_at, user_uuid, unit_cost, currency)
VALUES (9001, 4, 'Fictitious supplier', 'Valencia', '2026-10-27 09:00:00+00', '00000000-0000-4000-8000-000000000000', 15.00, 'EUR');
INSERT INTO asset_exits (asset_id, quantity, exit_type, assigned_to, office, created_at, user_uuid)
VALUES (9001, 9, 'consumption', NULL, 'Valencia', '2026-10-30 12:00:00+00', '00000000-0000-4000-8000-000000000000');

COMMIT;

SELECT count(*) AS seeded_events FROM telemetry_events;
