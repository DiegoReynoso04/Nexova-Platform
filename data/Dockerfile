# Imágenes del pipeline de desempeño de negocio (Prefect 3), en tres etapas que
# comparten la base (Python, dependencias con hashes, nexova_shared y el código):
#
# - `pipeline` (la última, la de por defecto): servidor de Prefect y worker del
#   perfil `pipelines` de Compose (D3 de docs/reporting/implementation-analysis.md).
#   La API no usa esta imagen ni instala Prefect (D1).
# - `scheduler`: el job nocturno de DEV-53 (perfil `nightly`). La base + supercronic
#   + `scripts/nightly_export.py` y `services/job_runner`, con un usuario no root.
#
# Contexto de build: data/. Contexto adicional `packages`: packages/ del
# monorepo (nexova_shared), que no está publicado y nunca se instala desde PyPI
# (ver data/pipelines/pyproject.toml):
#   docker build -t nexova-pipeline:dev --build-context packages=packages data
# El scheduler necesita además `scripts` y `services` (solo se copian
# nightly_export.py y los .py de job_runner; ver docker-compose.yml):
#   docker build --target scheduler -t nexova-nightly-scheduler:dev #     --build-context packages=packages --build-context scripts=scripts --build-context services=services data
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

# supercronic (disparador del job nocturno): UN binario fijado por versión y SHA-256,
# descargado SOLO aquí, en el build. Si el checksum no coincide, el build falla.
# Versión y checksums (los publica GitHub como `digest` del asset y coinciden con
# los calculados al descargar): github.com/aptible/supercronic/releases/tag/v0.2.51
# Para otra versión: cambiar los tres ARG juntos (o pasarlos con --build-arg).
FROM ${PYTHON_IMAGE} AS supercronic
ARG TARGETARCH
ARG SUPERCRONIC_VERSION=v0.2.51
ARG SUPERCRONIC_SHA256_AMD64=cc232108374e8e2b537045f2d5eaa1229f619db314c3ba6a14d38b35dc0aa123
ARG SUPERCRONIC_SHA256_ARM64=4ae22576a78223d8ccdf5f3b3660a5cbb5288416bf0ca96afc4a36d195932b94
RUN set -eu;     case "${TARGETARCH}" in       amd64) asset=supercronic-linux-amd64; sha="${SUPERCRONIC_SHA256_AMD64}" ;;       arm64) asset=supercronic-linux-arm64; sha="${SUPERCRONIC_SHA256_ARM64}" ;;       *) echo "supercronic: unsupported architecture '${TARGETARCH}'" >&2; exit 1 ;;     esac;     python -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], '/supercronic')"       "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${asset}";     echo "${sha}  /supercronic" | sha256sum -c -;     chmod 0755 /supercronic

FROM ${PYTHON_IMAGE} AS base

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

# --- scheduler: el job nocturno de DEV-53 (perfil `nightly` de Compose) -------------------
FROM base AS scheduler

COPY --from=supercronic /supercronic /usr/local/bin/supercronic

# Usuario no root. Sus dos carpetas de trabajo existen y son suyas: los CSV
# (`/data/raw`, montada desde el host en Compose) y los snapshots del pipeline.
# Su HOME guarda el estado del Prefect efímero que arranca cada corrida.
RUN groupadd --gid 10001 nexova     && useradd --uid 10001 --gid nexova --create-home --home-dir /home/nexova nexova     && mkdir -p /data/raw /data/eval/business_performance     && chown -R nexova:nexova /data/raw /data/eval /home/nexova

# Solo lo necesario del job: el script y los .py de job_runner (sin tests ni README).
# `scripts` y `services` son contextos adicionales: no los toca el .dockerignore de data/.
COPY --from=scripts nightly_export.py /scripts/nightly_export.py
COPY --from=services job_runner/*.py /services/job_runner/
# El crontab (0 2 * * * UTC) vive en el repo, junto a este Dockerfile.
COPY nightly.crontab /etc/nexova/nightly.crontab

# Sin analítica de Prefect ya viene de la base. TZ explícito: el cron es en UTC.
ENV TZ=UTC
USER nexova
WORKDIR /
# `-overlapping`: si una corrida sigue en marcha cuando llega el siguiente disparo, supercronic
# lanza igualmente el script y la segunda instancia aborta en silencio por el lock de la base
# (el estado `processing`). El lock es el único mecanismo de exclusión, como pide el ticket.
CMD ["supercronic", "-overlapping", "/etc/nexova/nightly.crontab"]

# --- pipeline: la imagen de por defecto (servidor de Prefect y worker) ---------------------
FROM base AS pipeline

EXPOSE 4200

# Por defecto, el servidor de Prefect (API y UI en el 4200). El worker del perfil
# sobrescribe el comando en docker-compose.yml.
CMD ["prefect", "server", "start", "--host", "0.0.0.0", "--port", "4200"]
