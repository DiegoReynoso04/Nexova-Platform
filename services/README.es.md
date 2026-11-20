# Carpeta `services`

Esta carpeta contiene **todos los servicios backend** (APIs y workers en segundo plano) relacionados con la compañía para el proyecto transversal de AI Engineering.

Cada subcarpeta dentro de `services/` debe corresponder a **un servicio concreto** (por ejemplo `admin-api`, `data-processor-worker`) e incluir su propia documentación técnica y funcional.

- **Propósito principal**: centralizar toda la lógica backend, APIs y consumidores de colas que dan soporte a los casos de uso de la compañía.
- **Recomendación**: documenta en este archivo (o en sub-READMEs) los servicios que vayas añadiendo, su objetivo, tecnología usada y cómo ejecutarlos.

## Servicios en este repositorio

| Servicio | Ruta | Objetivo | Stack | Estado |
|---|---|---|---|---|
| API de Nexova | [`api/`](./api/README.md) | Una sola app FastAPI: (1) capa HTTP sobre `packages/incident-analyzer` para el análisis del CSV de tickets de soporte de Nexova (Atención al Cliente, Roberto Díaz); (2) directorio de proveedores `/suppliers` persistido en TinyDB, con su seeder (Patricia Solís, RRHH); (3) autenticación AUTH-01: `/auth`, `/users`, `/profiles` (JWT, `User`/`Profile` en TinyDB, `create-admin`), obligatoria en las rutas de (1) y (2); después, el gestor centralizado de incidencias y el inventario (Supabase). Uso local, arrancada con Docker (`services/Dockerfile`, desde #infra-40) | Python 3.11+, FastAPI, Pydantic, TinyDB, uvicorn, libpass (bcrypt), python-jose | Fase 2 del analizador de incidentes; API de almacenamiento ligero (`docs/ligthweight-storage-api.md`); AUTH-01 (`docs/auth-api.md`) |
| Análisis de telemetría | [`telemetry/`](./telemetry/README.md) | No es un servicio desplegable: librería de la API de Nexova. Análisis con Pandas de `telemetry_events` para `GET /telemetry/report` (métricas técnicas) | Python, Pandas | Activo |
| Estado del job nocturno | [`job_runner/`](./job_runner/README.md) | No es un servicio desplegable: biblioteca con la máquina de estados y el lock (`processing`) de `ops.job_runs` del job nocturno de telemetría (`scripts/nightly_export.py`, DEV-53) | Python, SQLAlchemy | Activo |
| Cola de tareas | [`task_queue/`](./task_queue/README.es.md) | Biblioteca que corre en su propio proceso: la app de Celery (Redis como broker y result backend) con la que la API encola tareas y que ejecuta el servicio `worker` de Compose; Flower la monitoriza en `127.0.0.1:5555` (DEV-55) | Python, Celery, Redis | F1 en curso (parada 2: reintentos con backoff, dead letter queue `ops.task_dead_letters` y su migración) |

**Docker (ticket #infra-40):** la API corre en su propio contenedor, construido con [`Dockerfile`](./Dockerfile) con `services/` como contexto de build y `packages/` como contexto adicional; `docker compose up` desde la raíz del repositorio. Las dependencias salen de [`api/requirements.txt`](./api/requirements.txt), exportado de `uv.lock` (cómo regenerarlo: [`api/README.md`](./api/README.md#requirementstxt)). Guía completa: [`docs/local-development.md`](../docs/local-development.md).
