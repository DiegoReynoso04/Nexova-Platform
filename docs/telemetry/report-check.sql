-- Hand-written SQL for each metric of GET /telemetry/report, without Pandas, to square
-- them against the JSON. Read only. Guide: docs/telemetry/report-review.md.
-- Variables: start and end, the period.from and period.to of the JSON.
-- ASCII on purpose: PowerShell 5.1 pipes it with the console encoding.

\set ON_ERROR_STOP on
\pset footer off
SET TIME ZONE 'UTC';
BEGIN TRANSACTION READ ONLY;

\echo === events_per_day
SELECT to_char(d, 'YYYY-MM-DD') AS day, s AS service, count(e.event_id) AS events
FROM generate_series(date_trunc('day', :'start'::timestamptz), :'end'::timestamptz - interval '1 millisecond', interval '1 day') AS d
CROSS JOIN (VALUES ('backoffice'), ('api')) AS services(s)
LEFT JOIN telemetry_events e
  ON e.service = s AND e.timestamp >= d AND e.timestamp < d + interval '1 day'
 AND e.timestamp >= :'start'::timestamptz AND e.timestamp < :'end'::timestamptz
GROUP BY d, s
ORDER BY d, s DESC;

\echo === error_rate_by_type
WITH technical AS (
  SELECT to_char(timestamp, 'YYYY-MM-DD') AS day,
         CASE WHEN event_type IN ('form_submitted', 'page_load_recorded') THEN event_type || ':' || (tags ->> 'outcome') ELSE event_type END AS error_type,
         1 + coalesce((tags ->> 'suppressed_count')::int, 0) AS occurrences
  FROM telemetry_events
  WHERE timestamp >= :'start'::timestamptz AND timestamp < :'end'::timestamptz
    AND event_type NOT IN ('inbound_order_created', 'outbound_order_created', 'stock_threshold_triggered', 'kit_cost_variance_detected')
),
totals AS (SELECT day, sum(occurrences) AS total_events FROM technical GROUP BY day)
SELECT t.day, t.error_type,
       CASE WHEN t.error_type IN ('client_request_failed', 'frontend_error_captured', 'page_load_recorded:error', 'form_submitted:network_error', 'form_submitted:server_error') THEN 'system' ELSE 'rejected' END AS error_class,
       sum(t.occurrences) AS errors, o.total_events, sum(t.occurrences)::float8 / o.total_events AS error_rate
FROM technical t JOIN totals o USING (day)
WHERE t.error_type IN ('client_request_failed', 'frontend_error_captured', 'page_load_recorded:error', 'form_submitted:network_error', 'form_submitted:server_error',
                       'form_submitted:api_rejected', 'form_submitted:validation_error', 'form_submitted:session_expired',
                       'form_validation_failed', 'page_not_found_viewed', 'direct_stock_edit_rejected')
GROUP BY t.day, t.error_type, o.total_events
ORDER BY t.day, t.error_type;

\echo === page_load_latency_by_route
SELECT to_char(timestamp, 'YYYY-MM-DD') AS day, tags ->> 'route_template' AS route_template, tags ->> 'outcome' AS outcome,
       count(*) AS loads, avg((tags ->> 'duration_ms')::float8) AS avg_ms, max((tags ->> 'duration_ms')::float8) AS max_ms
FROM telemetry_events
WHERE timestamp >= :'start'::timestamptz AND timestamp < :'end'::timestamptz AND event_type = 'page_load_recorded'
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

\echo === dominant_event_types
SELECT event_type, service, count(*) AS events, count(*)::float8 / sum(count(*)) OVER () AS share
FROM telemetry_events
WHERE timestamp >= :'start'::timestamptz AND timestamp < :'end'::timestamptz
GROUP BY event_type, service
ORDER BY events DESC, event_type, service;

\echo === auth_failure_rate
SELECT to_char(timestamp, 'YYYY-MM-DD') AS day,
       count(*) FILTER (WHERE tags ->> 'outcome' = 'api_rejected') AS failed,
       count(*) FILTER (WHERE tags ->> 'outcome' = 'success') AS succeeded,
       count(*) AS attempts,
       (count(*) FILTER (WHERE tags ->> 'outcome' = 'api_rejected'))::float8 / count(*) AS failure_rate
FROM telemetry_events
WHERE timestamp >= :'start'::timestamptz AND timestamp < :'end'::timestamptz
  AND event_type = 'form_submitted' AND tags ->> 'form' = 'login' AND tags ->> 'outcome' IN ('api_rejected', 'success')
GROUP BY 1
ORDER BY 1;

ROLLBACK;
