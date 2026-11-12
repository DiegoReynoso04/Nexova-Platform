-- Read-only check of the reporting schema after its migration (stop 4): privileges of
-- PUBLIC and the Supabase roles, RLS, policies, ownership, Data API exposure and row
-- counts. Run it with: python -m business_performance.readonly (from data/pipelines).
-- Expected: every privilege false, public_grants = 0, RLS on, 0 policies.
-- Guide: docs/reporting/implementation-review.md section 6. ASCII on purpose.

\set ON_ERROR_STOP on

-- anon, authenticated and service_role: no privilege on the schema or the tables.
SELECT r.rolname AS role,
       has_schema_privilege(r.rolname, 'reporting', 'USAGE') AS schema_usage,
       has_schema_privilege(r.rolname, 'reporting', 'CREATE') AS schema_create,
       has_table_privilege(r.rolname, 'reporting.pipeline_runs', 'SELECT') AS runs_select,
       has_table_privilege(r.rolname, 'reporting.pipeline_runs', 'INSERT,UPDATE,DELETE,TRUNCATE') AS runs_write,
       has_table_privilege(r.rolname, 'reporting.weekly_office_program_performance', 'SELECT') AS weekly_select,
       has_table_privilege(r.rolname, 'reporting.weekly_office_program_performance', 'INSERT,UPDATE,DELETE,TRUNCATE')
         AS weekly_write
FROM pg_roles r
WHERE r.rolname IN ('anon', 'authenticated', 'service_role')
ORDER BY 1;

-- PUBLIC: no grant on the schema or on its tables.
SELECT (SELECT count(*) FROM pg_namespace n, aclexplode(n.nspacl) a
         WHERE n.nspname = 'reporting' AND a.grantee = 0)
     + (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace, aclexplode(c.relacl) a
         WHERE n.nspname = 'reporting' AND a.grantee = 0) AS public_grants;

-- RLS on, no policies, owned by the role of the connection (the one of the API).
SELECT c.relname AS table_name,
       c.relrowsecurity AS rls_enabled,
       (SELECT count(*) FROM pg_policies p WHERE p.schemaname = 'reporting' AND p.tablename = c.relname) AS policies,
       pg_get_userbyid(c.relowner) = current_user AS owned_by_current_role
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'reporting' AND c.relkind = 'r'
ORDER BY 1;

-- Supabase Data API: reporting must not be among the exposed schemas (no rows elsewhere).
SELECT setting AS authenticator_setting
FROM pg_roles, unnest(rolconfig) AS setting
WHERE rolname = 'authenticator' AND setting LIKE 'pgrst.db_schemas=%';

-- What the pipeline has written.
SELECT (SELECT count(*) FROM reporting.pipeline_runs) AS pipeline_runs,
       (SELECT count(*) FROM reporting.weekly_office_program_performance) AS weekly_rows;
