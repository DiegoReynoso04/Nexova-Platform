# Imagen de desarrollo de services/api (FastAPI), ticket #infra-40.
#
# Contexto de build: services/. Contexto adicional `packages`: packages/ del
# monorepo (nexova_shared e incident_analyzer), que no están publicados y nunca
# se instalan desde PyPI (ver services/api/pyproject.toml):
#   docker build -t nexova-api:dev --build-context packages=packages --build-context pipelines=data/pipelines services
# En Compose (F4) los contextos adicionales se declaran con `additional_contexts`.
# Del contexto `pipelines` solo entran business_performance/__init__.py y
# trigger.py: el disparo manual, de librería estándar. Nunca Prefect ni el ETL.
#
# Sin secretos: ni ENV ni ARG con claves. La configuración llega en tiempo de
# ejecución desde el .env de la raíz (ver .env.example).
#
# Targets (DEV-55): `api` (el último, el de por defecto) sirve a la API y al worker
# de Celery (mismo código y mismas dependencias, otro comando en Compose); `flower`
# añade encima el grupo `flower` de uv (requirements-flower.txt), solo de desarrollo.

# Misma versión que el venv de services/api (3.14.6), en Debian (glibc 2.41):
# las dependencias de uv.lock tienen wheels manylinux para cp314.
ARG PYTHON_IMAGE=python:3.14.6-slim

# Paquetes del monorepo, limpios. El .dockerignore de services/ no se aplica al
# contexto adicional `packages`, así que la caché de bytecode del host
# (__pycache__, *.pyc) se borra aquí y la imagen final solo copia el resultado.
FROM ${PYTHON_IMAGE} AS monorepo-packages
COPY --from=packages shared/nexova_shared /packages/shared/nexova_shared
COPY --from=packages incident-analyzer/incident_analyzer /packages/incident-analyzer/incident_analyzer
COPY --from=pipelines business_performance/__init__.py business_performance/trigger.py /pipelines/business_performance/
RUN find /packages \( -name __pycache__ -o -name "*.pyc" \) -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE} AS runtime

# uv fijado a la misma versión que generó api/requirements.txt (uv export).
# Binario estático copiado de la imagen oficial: sin pip ni red en esta capa.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Paquetes del monorepo por ruta, sin instalarlos: instalarlos pediría
    # setuptools a PyPI (la imagen no lo trae) y, en desarrollo, una copia
    # instalada taparía el bind mount de packages/ (F4).
    # /app/api (DEV-55): Celery solo añade el directorio actual a sys.path mientras
    # importa la app (`celery.utils.imports.cwd_in_path`); la clase base de las tareas
    # y sus importaciones (job_runner, telemetry) se resuelven después, sin él.
    PYTHONPATH=/app/api:/packages/shared:/packages/incident-analyzer:/pipelines

WORKDIR /app/api

# 1. Dependencias de terceros: versiones exactas de uv.lock, con hashes.
#    Solo se reconstruye si cambia requirements.txt.
COPY api/requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache --require-hashes -r requirements.txt

# 2. Paquetes del monorepo, aparte y sin dependencias (no declaran ninguna):
#    solo el código importable, sin tests, metadatos de build, TypeScript ni
#    caché de bytecode (ver la etapa monorepo-packages).
COPY --from=monorepo-packages /packages /packages
COPY --from=monorepo-packages /pipelines /pipelines

# 3. Código de la API (lo que más cambia, al final).
COPY api/app ./app
# Análisis de telemetría (Pandas): junto a `app`, para que se importe como
# `telemetry` sin tocar PYTHONPATH (D1 de docs/telemetry/report-analysis.md).
COPY telemetry ./telemetry
# Endpoints del reporte de negocio: librería de la API, como `telemetry`
# (se importa como `reporting`). Sin ETL: ver services/reporting/README.md.
COPY reporting ./reporting
# Cola de tareas (DEV-55, A5): la API la importa para encolar y el worker la ejecuta
# (`celery -A task_queue.celery_app worker`). Se importa como `task_queue`.
COPY task_queue ./task_queue
# job_runner (DEV-53): task_queue reutiliza su redacción de errores (A12) y las reglas
# de DATABASE_URL y del esquema ops. Solo SQLAlchemy y la librería estándar.
COPY job_runner ./job_runner

# Usuario sin privilegios para el worker y Flower (`user: nexova` en Compose). La API
# sigue como root: escribe en el bind mount de TinyDB (services/api/data) del host.
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin nexova

EXPOSE 8000

# Arranque de services/api/README.md, con --reload (lo pide el brief) y escuchando
# en todas las interfaces del contenedor.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--reload"]

# Flower (DEV-55, A14): las dependencias de la API (ya instaladas) más el grupo
# `flower`. Con --require-hashes, el archivo trae todas las versiones exactas.
FROM runtime AS flower
COPY api/requirements-flower.txt ./requirements-flower.txt
RUN uv pip install --system --no-cache --require-hashes -r requirements-flower.txt
EXPOSE 5555
USER nexova
CMD ["celery", "-A", "task_queue.celery_app", "flower", "--address=0.0.0.0", "--port=5555"]

# Imagen de la API y del worker: el último target, el de `docker build` sin --target.
FROM runtime AS api
