# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

## Scripts in this folder

| Script | What it does | Docs |
|---|---|---|
| `analyze.py` | Nexova incident analyzer CLI (validation, metrics, `results.csv` export) | [`packages/incident-analyzer/README.md`](../packages/incident-analyzer/README.md) |
| `seed_incidents.py` | Loads the helpdesk incidents CSV into the centralized incident manager (idempotent; run with the `services/api` virtualenv) | [`services/api/README.md`](../services/api/README.md#seed-de-datos-históricos-scriptsseed_incidentspy) |
| `seed_volume.py` | Synthetic volume seed (thousands of incidents, hundreds of suppliers, inventory assets with hundreds of orders) for **test databases only**: deterministic, idempotent, refuses the demo data and non-local PostgreSQL | [`docs/caching-analysis.md`](../docs/caching-analysis.md) §2 |
| `bench_reads.py` | Bursts of identical GET requests against the API (first request, p50/p95, identical responses, same for another account); standard library only, read-only, credentials via environment variables | [`docs/caching-analysis.md`](../docs/caching-analysis.md) §2 |
| `validate_event_schemas.py` | Validates `docs/telemetry/event-schemas.json` (closed subset of JSON Schema draft-07) and its consistency with `docs/telemetry/telemetry-plan.md`: same events, metadata and allowlists, and every JSON example in the plan validates; standard library only. `--dump-examples <dir>` writes the examples for `ajv-cli` | [`docs/telemetry/telemetry-plan.md`](../docs/telemetry/telemetry-plan.md) §9 |
| `nightly_export.py` | Nightly telemetry job (DEV-53): exports the previous UTC day of `telemetry_events` to `data/raw/telemetry_YYYY-MM-DD.csv` (privacy projection, whitelisted tag keys, atomic write, never overwritten) and runs the pipeline as a subprocess, under the `ops.job_runs` state machine (`processing` is the lock; idempotent per day). Independent of the API. Run with the `data/pipelines` environment (needs Prefect); `TARGET_DATE=YYYY-MM-DD` overrides the day; exit 0 completed/skipped/locked, 1 failed, 2 configuration (no row). Scheduled by the `nightly` Compose profile (supercronic, `0 2 * * *` UTC) | [`docs/telemetry/nightly-export-review.md`](../docs/telemetry/nightly-export-review.md), [`services/job_runner/README.md`](../services/job_runner/README.md) |

> _Spanish version: [README.es.md](./README.es.md)._
