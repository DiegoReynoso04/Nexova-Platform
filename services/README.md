# `services` folder

This folder contains **all the backend services** (APIs and background workers) related to the company for the cross-functional AI Engineering project.

Each subfolder inside `services/` must correspond to **one specific service** (for example: `admin-api`, `data-processor-worker`) and include its own technical and functional documentation.

- **Main purpose**: to centralize all the backend logic, APIs, and queue consumers that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the services you add, their objective, the technology used, and how to run them.

## Services in this repository

| Service | Path | Objective | Stack | Status |
|---|---|---|---|---|
| Nexova API | [`api/`](./api/README.md) | Single FastAPI app: (1) HTTP layer over `packages/incident-analyzer` for Nexova's support-ticket CSV analysis (Customer Support, Roberto Díaz); (2) supplier directory `/suppliers` persisted in TinyDB, with its seeder (Patricia Solís, HR); (3) AUTH-01 authentication: `/auth`, `/users`, `/profiles` (JWT, `User`/`Profile` in TinyDB, `create-admin`), required on the routes of (1) and (2); later, the centralized incident manager and the inventory (Supabase). Local use, run with Docker (`services/Dockerfile`, since #infra-40) | Python 3.11+, FastAPI, Pydantic, TinyDB, uvicorn, libpass (bcrypt), python-jose | Phase 2 of the incident analyzer; lightweight storage API (`docs/ligthweight-storage-api.md`); AUTH-01 (`docs/auth-api.md`) |
| Telemetry analysis | [`telemetry/`](./telemetry/README.md) | Not a deployable service: library of the Nexova API. Pandas analysis of `telemetry_events` behind `GET /telemetry/report` (technical metrics) | Python, Pandas | Active |
| Nightly job state | [`job_runner/`](./job_runner/README.md) | Not a deployable service: library with the `ops.job_runs` state machine and lock (`processing`) of the nightly telemetry job (`scripts/nightly_export.py`, DEV-53) | Python, SQLAlchemy | Active |
| Task queue | [`task_queue/`](./task_queue/README.md) | Library run as its own process: the Celery app (Redis broker and result backend) that the API uses to enqueue tasks and the `worker` Compose service runs; Flower monitors it on `127.0.0.1:5555` (DEV-55) | Python, Celery, Redis | F1 in progress (stop 1: Redis, worker and Flower with a trivial task) |

**Docker (ticket #infra-40):** the API runs in its own container, built from [`Dockerfile`](./Dockerfile) with `services/` as the build context and `packages/` as an additional context; `docker compose up` from the repository root. Dependencies come from [`api/requirements.txt`](./api/requirements.txt), exported from `uv.lock` (how to regenerate it: [`api/README.md`](./api/README.md#requirementstxt)). Full guide: [`docs/local-development.md`](../docs/local-development.md) (Spanish).

> _Spanish version: [README.es.md](./README.es.md)._
