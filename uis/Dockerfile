# Imagen de desarrollo del contenedor de interfaces (#infra-40): uis/website en
# el 3000 y uis/backoffice en el 3001, arrancados por start.sh.
#
# Contexto de build: uis/
#   docker build -t nexova-ui:dev uis
#
# Sin secretos: ni ENV ni ARG con claves. La configuración (API_INTERNAL_URL,
# NEXT_PUBLIC_*) llega en ejecución desde el .env de la raíz (ver .env.example).

# Node 24 fijado (los tests del backoffice usan Node 24; ver AGENTS.md §4).
FROM node:24.20.0-alpine

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app/uis

# Dependencias, por app y antes que el código (caché de capas):
# - uis/website es HTML estático sin package.json: no hay nada que instalar.
# - uis/backoffice: npm ci desde su package-lock.json, sin modificarlo, con las
#   dependencias de desarrollo (next dev las necesita). En Alpine instala las
#   variantes musl de los binarios nativos (@next/swc, lightningcss y
#   @tailwindcss/oxide), que el lockfile ya incluye.
COPY backoffice/package.json backoffice/package-lock.json ./backoffice/
RUN cd backoffice \
    && npm ci --no-audit --no-fund \
    && npm cache clean --force

# Código de las dos apps y el arranque (lo que más cambia, al final).
COPY website ./website
COPY backoffice ./backoffice
COPY serve-website.mjs start.sh ./

EXPOSE 3000 3001

CMD ["sh", "./start.sh"]
