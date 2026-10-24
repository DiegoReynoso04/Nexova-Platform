#!/bin/sh
# Arranque del contenedor de interfaces en desarrollo (#infra-40): el website
# en el 3000 y el backoffice en el 3001, en un solo contenedor. Producción es
# otro modo (fase F6).
#
# - SIGTERM/SIGINT (docker stop, Ctrl+C) se reenvían a los dos procesos.
# - Si uno termina, se para el otro y el script sale con un código distinto
#   de 0, para que el contenedor no se quede vivo a medias.
#
# POSIX sh de busybox (comprobado en node:24.20.0-alpine, BusyBox 1.37):
# - su `wait -n` espera a todos y devuelve 0, así que se vigila con `kill -0`;
# - cada app arranca en su propio grupo de procesos (`setsid`) y las señales
#   van al grupo: si `next dev` muere de golpe, su `next-server` queda huérfano
#   y, sin esto, mantendría vivo el contenedor.
#
# `next dev --webpack`: comprobado en #infra-40 (F4) que, en este contenedor,
# Turbopack (el bundler por defecto) no aplica los cambios del código montado,
# ni con sondeo ni con cambios hechos dentro del contenedor, mientras que webpack
# con WATCHPACK_POLLING (lo pone docker-compose.yml) recarga en unos 2 s.

set -u

cd "$(dirname "$0")"

(exec setsid node serve-website.mjs) &
website_pid=$!

(cd backoffice && exec setsid node_modules/.bin/next dev --webpack --hostname 0.0.0.0 --port 3001) &
backoffice_pid=$!

stopping=0

# Señal a todo el grupo de procesos de una app (su PID es el del grupo).
signal_group() {
  kill "-$1" "-$2" 2>/dev/null
}

group_alive() {
  kill -0 "-$1" 2>/dev/null
}

# TERM a los dos grupos; KILL a lo que siga vivo a los 10 s.
stop_all() {
  signal_group TERM "$website_pid"
  signal_group TERM "$backoffice_pid"
  tries=0
  while { group_alive "$website_pid" || group_alive "$backoffice_pid"; } && [ "$tries" -lt 20 ]; do
    sleep 0.5
    tries=$((tries + 1))
  done
  signal_group KILL "$website_pid"
  signal_group KILL "$backoffice_pid"
  wait
}

on_signal() {
  stopping=1
}

trap on_signal TERM INT

while [ "$stopping" -eq 0 ] && kill -0 "$website_pid" 2>/dev/null && kill -0 "$backoffice_pid" 2>/dev/null; do
  sleep 0.5
done

if [ "$stopping" -eq 1 ]; then
  stop_all
  exit 0
fi

if ! kill -0 "$website_pid" 2>/dev/null; then
  wait "$website_pid"
  status=$?
  echo "start.sh: el website terminó (código $status); se para el backoffice" >&2
else
  wait "$backoffice_pid"
  status=$?
  echo "start.sh: el backoffice terminó (código $status); se para el website" >&2
fi

stop_all

if [ "$status" -eq 0 ]; then
  status=1
fi
exit "$status"
