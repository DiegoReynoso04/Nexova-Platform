-- Read-only snapshot of the demo, before and after the business pipeline (stop 4).
-- Run it with: python -m business_performance.readonly (from data/pipelines), which
-- wraps it in SET TRANSACTION READ ONLY + ROLLBACK. Only counts and md5 fingerprints
-- are printed: no identifiers, users, suppliers or URLs. ASCII on purpose.
-- Guide: docs/reporting/implementation-review.md section 6.

\set ON_ERROR_STOP on

-- The server and the Supabase roles (the migration revokes from them).
SELECT current_setting('server_version') AS server_version,
       (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS current_role_is_superuser,
       (SELECT string_agg(rolname, ',' ORDER BY rolname) FROM pg_roles
         WHERE rolname IN ('anon', 'authenticated', 'service_role')) AS supabase_roles;

-- The reporting schema (before the migration: all false).
SELECT to_regnamespace('reporting') IS NOT NULL AS reporting_schema_exists,
       to_regclass('reporting.pipeline_runs') IS NOT NULL AS pipeline_runs_exists,
       to_regclass('reporting.weekly_office_program_performance') IS NOT NULL AS weekly_table_exists;

-- telemetry_events (immutable). The fingerprint covers the events before today
-- 00:00 UTC, so using the backoffice during the walk-through does not change it;
-- events_total may grow with that use (the pipeline never writes here).
SELECT count(*) AS events_total,
       count(*) FILTER (WHERE "timestamp" < date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
         AS events_before_today,
       md5(string_agg(event_id::text || '|' || event_type || '|' || "timestamp"::text, ',' ORDER BY event_id)
           FILTER (WHERE "timestamp" < date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'))
         AS fingerprint_before_today
FROM telemetry_events;

-- The 4 business events of the week 2026-11-02 (what the run will aggregate),
-- grouped, without any order id: the expected KPIs come from here.
SELECT e.event_type,
       e.tags->>'office' AS office,
       COALESCE(e.tags->>'programme_id', '_unassigned') AS programme_id,
       e.tags->>'currency' AS currency,
       e.tags->>'quantity' AS quantity,
       e.tags->>'unit_cost' AS unit_cost,
       count(*) AS events,
       count(DISTINCT COALESCE(e.tags->>'inbound_order_id', e.tags->>'outbound_order_id')) AS distinct_orders
FROM telemetry_events e
WHERE e.event_type IN ('inbound_order_created', 'outbound_order_created',
                       'stock_threshold_triggered', 'kit_cost_variance_detected')
  AND e."timestamp" >= '2026-11-02 00:00:00+00'
  AND e."timestamp" <  '2026-11-09 00:00:00+00'
GROUP BY 1, 2, 3, 4, 5, 6
ORDER BY 1, 2;

-- Inventory tables (insert only): count, last id and a fingerprint of every row.
SELECT 'assets' AS table_name, count(*) AS row_count, max(id) AS max_id,
       md5(string_agg(t::text, '|' ORDER BY id)) AS fingerprint
FROM assets t
UNION ALL
SELECT 'asset_entries', count(*), max(id), md5(string_agg(t::text, '|' ORDER BY id)) FROM asset_entries t
UNION ALL
SELECT 'asset_exits', count(*), max(id), md5(string_agg(t::text, '|' ORDER BY id)) FROM asset_exits t;
