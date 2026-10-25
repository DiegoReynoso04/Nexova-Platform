# Imagen de desarrollo de services/api (FastAPI), ticket #infra-40.
#
# Contexto de build: services/. Contexto adicional `packages`: packages/ del
# monorepo (nexova_shared e incident_analyzer), que no están publicados y nunca
# se instalan desde PyPI (ver services/api/pyproject.toml):
#   docker build -t nexova-api:dev --build-context packages=packages services
# En Compose (F4) el contexto adicional se declara con `additional_contexts`.
#
# Sin secretos: ni ENV ni ARG con claves. La configuración llega en tiempo de
# ejecución desde el .env de la raíz (ver .env.example).

# Misma versión que el venv de services/api (3.14.6), en Debian (glibc 2.41):
# las 28 dependencias de uv.lock tienen wheels manylinux para cp314.
ARG PYTHON_IMAGE=python:3.14.6-slim

# Paquetes del monorepo, limpios. El .dockerignore de services/ no se aplica al
# contexto adicional `packages`, así que la caché de bytecode del host
# (__pycache__, *.pyc) se borra aquí y la imagen final solo copia el resultado.
FROM ${PYTHON_IMAGE} AS monorepo-packages
COPY --from=packages shared/nexova_shared /packages/shared/nexova_shared
COPY --from=packages incident-analyzer/incident_analyzer /packages/incident-analyzer/incident_analyzer
RUN find /packages \( -name __pycache__ -o -name "*.pyc" \) -prune -exec rm -rf {} +

FROM ${PYTHON_IMAGE}

# uv fijado a la misma versión que generó api/requirements.txt (uv export).
# Binario estático copiado de la imagen oficial: sin pip ni red en esta capa.
COPY --from=ghcr.io/astral-sh/uv:0.12.21 /uv /usr/local/bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Paquetes del monorepo por ruta, sin instalarlos: instalarlos pediría
    # setuptools a PyPI (la imagen no lo trae) y, en desarrollo, una copia
    # instalada taparía el bind mount de packages/ (F4).
    PYTHONPATH=/packages/shared:/packages/incident-analyzer

WORKDIR /app/api

# 1. Dependencias de terceros: versiones exactas de uv.lock, con hashes.
#    Solo se reconstruye si cambia requirements.txt.
COPY api/requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache --require-hashes -r requirements.txt

# 2. Paquetes del monorepo, aparte y sin dependencias (no declaran ninguna):
#    solo el código importable, sin tests, metadatos de build, TypeScript ni
#    caché de bytecode (ver la etapa monorepo-packages).
COPY --from=monorepo-packages /packages /packages

# 3. Código de la API (lo que más cambia, al final).
COPY api/app ./app

EXPOSE 8000

# Arranque de services/api/README.md, con --reload (lo pide el brief) y escuchando
# en todas las interfaces del contenedor.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--reload"]
