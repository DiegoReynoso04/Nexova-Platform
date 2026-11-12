# Imagen del pipeline de desempeño de negocio (Prefect 3): servidor de Prefect y
# worker del perfil `pipelines` de Compose (D3 de
# docs/reporting/implementation-analysis.md). La API no usa esta imagen ni
# instala Prefect (D1).
#
# Contexto de build: data/. Contexto adicional `packages`: packages/ del
# monorepo (nexova_shared), que no está publicado y nunca se instala desde PyPI
# (ver data/pipelines/pyproject.toml):
#   docker build -t nexova-pipeline:dev --build-context packages=packages data
#
# Sin secretos: ni ENV ni ARG con claves. El worker lee la credencial de un
# block de Prefect, no del .env (D5).

# Misma versión que la imagen de la API y que el venv de data/pipelines (3.14.6).
ARG PYTHON_IMAGE=python:3.14.6-slim

# nexova_shared, limpio: el .dockerignore de data/ no se aplica al contexto
# adicional `packages`, así que la caché de bytecode del host se borra aquí.
FROM ${PYTHON_IMAGE} AS monorepo-packages
COPY --from=packages shared/nexova_shared /packages/shared/nexova_shared
RUN find /packages \( -name __pycache__ -o -name "*.pyc" \) -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE}

# uv fijado a la misma versión que generó pipelines/requirements.txt (uv export).
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Código del pipeline y paquetes del monorepo por ruta, sin instalarlos
    # (como la API): pipeline.py y business_performance desde /data/pipelines,
    # la transformación pura desde /data/process y nexova_shared.
    PYTHONPATH=/data/pipelines:/data/process:/packages/shared \
    # Sin analítica anónima de Prefect: la del servidor y la del cliente (SDK).
    # Las fuerza también business_performance/_bootstrap.py antes de importar Prefect.
    PREFECT_SERVER_ANALYTICS_ENABLED=false \
    DO_NOT_TRACK=1

WORKDIR /data/pipelines

# 1. Dependencias de terceros: versiones exactas de uv.lock, con hashes.
COPY pipelines/requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache --require-hashes -r requirements.txt

# 2. nexova_shared, sin dependencias (no declara ninguna).
COPY --from=monorepo-packages /packages /packages

# 3. Código del pipeline (lo que más cambia, al final). Sin venv, tests ni
#    datos: ver data/.dockerignore.
COPY pipelines /data/pipelines
COPY process /data/process

EXPOSE 4200

# Por defecto, el servidor de Prefect (API y UI en el 4200). El worker del perfil
# sobrescribe el comando en docker-compose.yml.
CMD ["prefect", "server", "start", "--host", "0.0.0.0", "--port", "4200"]
