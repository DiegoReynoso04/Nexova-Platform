-- Hand-written check of the 4 KPIs: recomputes them from telemetry_events with plain
-- GROUP BY (no code of the pipeline involved) and compares them with
-- reporting.weekly_office_program_performance, both ways. Read only.
-- Guide: docs/reporting/implementation-review.md (stop 2). ASCII on purpose.
--
-- Weeks compared: those covered by a completed run in reporting.pipeline_runs.
-- Expected: "missing_or_different" = 0 and "unexpected" = 0.

\set ON_ERROR_STOP on

WITH weeks AS (
  SELECT DISTINCT gs::date AS week_start
  FROM reporting.pipeline_runs r,
       generate_series(r.week_from, r.week_to, interval '7 days') AS gs
  WHERE r.status = 'completed'
),
business AS (
  SELECT e.event_type,
         e.tags->>'office' AS office,
         COALESCE(e.tags->>'programme_id', '_unassigned') AS programme_id,
         e.tags->>'currency' AS currency,
         (date_trunc('week', e."timestamp" AT TIME ZONE 'UTC'))::date AS week_start,
         COALESCE(e.tags->>'inbound_order_id', e.tags->>'outbound_order_id') AS order_id,
         (e.tags->>'quantity')::integer AS quantity,
         (e.tags->>'unit_cost')::numeric AS unit_cost,
         row_number() OVER (
           PARTITION BY e.event_type, e.tags->>'office',
                        (date_trunc('week', e."timestamp" AT TIME ZONE 'UTC'))::date,
                        COALESCE(e.tags->>'inbound_order_id', e.tags->>'outbound_order_id')
           ORDER BY e."timestamp", e.event_id) AS nth
  FROM telemetry_events e
  WHERE e.event_type IN ('inbound_order_created', 'outbound_order_created',
                         'stock_threshold_triggered', 'kit_cost_variance_detected')
),
expected AS (
  SELECT b.office, b.programme_id, b.week_start,
         COALESCE(sum(b.unit_cost * b.quantity) FILTER (WHERE b.event_type = 'inbound_order_created'), 0)
           AS total_material_cost,
         count(*) FILTER (WHERE b.event_type = 'outbound_order_created')::integer AS kits_delivered_count,
         count(*) FILTER (WHERE b.event_type = 'stock_threshold_triggered')::integer AS shortage_events_count,
         count(*) FILTER (WHERE b.event_type = 'kit_cost_variance_detected')::integer AS cost_variance_events_count,
         min(b.currency) AS currency
  FROM business b
  JOIN weeks w USING (week_start)
  WHERE b.nth = 1  -- one order counts once per week (dedup by order id)
  GROUP BY b.office, b.programme_id, b.week_start
),
actual AS (
  SELECT office, programme_id, week_start, total_material_cost, kits_delivered_count,
         shortage_events_count, cost_variance_events_count, currency
  FROM reporting.weekly_office_program_performance
  JOIN weeks USING (week_start)
)
SELECT (SELECT count(*) FROM (SELECT * FROM expected EXCEPT SELECT * FROM actual) AS d) AS missing_or_different,
       (SELECT count(*) FROM (SELECT * FROM actual EXCEPT SELECT * FROM expected) AS d) AS unexpected,
       (SELECT count(*) FROM actual) AS rows_compared,
       (SELECT count(*) FROM weeks) AS weeks_compared;

-- The table itself, for the eye (the KPIs of the guide).
SELECT week_start, office, programme_id, total_material_cost, kits_delivered_count,
       shortage_events_count, cost_variance_events_count, currency
FROM reporting.weekly_office_program_performance
ORDER BY week_start, office, programme_id;

-- No duplicates by the natural key (the unique constraint makes this 0 by design).
SELECT count(*) AS duplicated_cells
FROM (SELECT office, programme_id, week_start FROM reporting.weekly_office_program_performance
      GROUP BY 1, 2, 3 HAVING count(*) > 1) AS d;

-- The run log.
SELECT trigger, status, phase, week_from, week_to, source_rows_read, rows_rejected,
       duplicates_collapsed, rows_upserted, rows_deleted, error_class,
       quality->'optional_steps' AS optional_steps
FROM reporting.pipeline_runs
ORDER BY started_at;
