# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

## Scripts in this folder

| Script | What it does | Docs |
|---|---|---|
| `analyze.py` | Nexova incident analyzer CLI (validation, metrics, `results.csv` export) | [`packages/incident-analyzer/README.md`](../packages/incident-analyzer/README.md) |
| `seed_incidents.py` | Loads the helpdesk incidents CSV into the centralized incident manager (idempotent; run with the `services/api` virtualenv) | [`services/api/README.md`](../services/api/README.md#seed-de-datos-históricos-scriptsseed_incidentspy) |

> _Spanish version: [README.es.md](./README.es.md)._
