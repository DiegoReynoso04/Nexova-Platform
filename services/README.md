# `services` folder

This folder contains **all the backend services** (APIs and background workers) related to the company for the cross-functional AI Engineering project.

Each subfolder inside `services/` must correspond to **one specific service** (for example: `admin-api`, `data-processor-worker`) and include its own technical and functional documentation.

- **Main purpose**: to centralize all the backend logic, APIs, and queue consumers that support the company's use cases.
- **Recommendation**: document in this file (or in sub-READMEs) the services you add, their objective, the technology used, and how to run them.

## Services in this repository

| Service | Path | Objective | Stack | Status |
|---|---|---|---|---|
| Nexova API | [`api/`](./api/README.md) | Single FastAPI app: (1) HTTP layer over `packages/incident-analyzer` for Nexova's support-ticket CSV analysis (Customer Support, Roberto Díaz); (2) supplier directory `/suppliers` persisted in TinyDB, with its seeder (Patricia Solís, HR); (3) AUTH-01 authentication: `/auth`, `/users`, `/profiles` (JWT, `User`/`Profile` in TinyDB, `create-admin`), required on the routes of (1) and (2); later, the centralized incident manager and the inventory (Supabase). Local use, run with Docker (`services/Dockerfile`, since #infra-40) | Python 3.11+, FastAPI, Pydantic, TinyDB, uvicorn, libpass (bcrypt), python-jose | Phase 2 of the incident analyzer; lightweight storage API (`docs/ligthweight-storage-api.md`); AUTH-01 (`docs/auth-api.md`) |

**Docker (ticket #infra-40):** the API runs in its own container, built from [`Dockerfile`](./Dockerfile) with `services/` as the build context and `packages/` as an additional context; `docker compose up` from the repository root. Dependencies come from [`api/requirements.txt`](./api/requirements.txt), exported from `uv.lock` (how to regenerate it: [`api/README.md`](./api/README.md#requirementstxt)). Full guide: [`docs/local-development.md`](../docs/local-development.md) (Spanish).

> _Spanish version: [README.es.md](./README.es.md)._
