"""Ráfagas de GET idénticos contra la API, para medir latencias (ticket de caching, D11).

Solo librería estándar (`http.client`): se ejecuta con cualquier Python ≥ 3.11,
también dentro del contenedor de la API. **Solo hace GET** (más un `POST
/auth/login` para obtener el token): no escribe nada. Aun así, apúntalo
siempre a una API de medición con bases de prueba, nunca a la demo
(docs/caching-analysis.md §2).

Para cada ruta, en el orden indicado:

1. **Primera petición** (`first_ms`): con la API recién arrancada, o pasado el
   TTL, es un fallo de caché. Si la ruta ya se pidió, puede ser un acierto.
2. `--warmup` peticiones que no cuentan.
3. `-n` peticiones idénticas (misma URL y mismo token): p50, p95, mínimo y
   máximo, en ms y en cliente.

También se comprueba si las N respuestas son idénticas y, con una segunda
cuenta (`BENCH_OTHER_*`), si la respuesta es la misma para otro usuario.

Credenciales por variables de entorno, nunca como argumentos (los argumentos
se ven en la lista de procesos):

    BENCH_EMAIL, BENCH_PASSWORD               cuenta principal (obligatoria)
    BENCH_OTHER_EMAIL, BENCH_OTHER_PASSWORD   segunda cuenta (opcional)

Uso:

    python scripts/bench_reads.py --base-url http://localhost:8100 -n 50 \\
        /inventory/products /inventory/products/1 "/api/incidents?status=open"

Salida: una línea JSON por ruta (stdout). Códigos: 0 bien; 1 configuración o
login fallido; 2 la API no responde.
"""

import argparse
import hashlib
import http.client
import json
import os
import statistics
import sys
import time
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass

TIMEOUT_SECONDS = 120


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    https: bool

    def connect(self) -> http.client.HTTPConnection:
        if self.https:
            return http.client.HTTPSConnection(self.host, self.port, timeout=TIMEOUT_SECONDS)
        return http.client.HTTPConnection(self.host, self.port, timeout=TIMEOUT_SECONDS)


def parse_target(base_url: str) -> Target:
    url = urllib.parse.urlparse(base_url)
    if url.scheme not in ("http", "https") or not url.hostname:
        raise ValueError("--base-url must be an http(s) URL")
    return Target(url.hostname, url.port or (443 if url.scheme == "https" else 80), url.scheme == "https")


def login(target: Target, email: str, password: str) -> str:
    connection = target.connect()
    body = urllib.parse.urlencode({"username": email, "password": password})
    connection.request("POST", "/auth/login", body, {"Content-Type": "application/x-www-form-urlencoded"})
    response = connection.getresponse()
    data = response.read()
    if response.status != 200:
        raise PermissionError(f"login failed with status {response.status}")
    return str(json.loads(data)["access_token"])


def get(connection: http.client.HTTPConnection, path: str, token: str) -> tuple[int, bytes, float]:
    start = time.perf_counter()
    connection.request("GET", path, headers={"Authorization": f"Bearer {token}"})
    response = connection.getresponse()
    body = response.read()
    return response.status, body, (time.perf_counter() - start) * 1000


def percentile(sorted_values: list[float], fraction: float) -> float:
    """Percentil por rango más cercano (p95 de 50 valores = el 48.º)."""
    index = max(0, min(len(sorted_values) - 1, round(fraction * len(sorted_values)) - 1))
    return sorted_values[index]


def rows_in(body: bytes) -> int | None:
    try:
        parsed = json.loads(body)
    except ValueError:
        return None
    return len(parsed) if isinstance(parsed, list) else None


def bench(target: Target, path: str, token: str, other_token: str | None, n: int, warmup: int, label: str) -> dict:
    connection = target.connect()
    status, first_body, first_ms = get(connection, path, token)
    for _ in range(warmup):
        get(connection, path, token)
    times: list[float] = []
    digests = {hashlib.sha256(first_body).hexdigest()}
    body = first_body
    for _ in range(n):
        status, body, elapsed = get(connection, path, token)
        times.append(elapsed)
        digests.add(hashlib.sha256(body).hexdigest())
    times.sort()
    result = {
        "label": label,
        "endpoint": f"GET {path}",
        "status": status,
        "n": n,
        "first_ms": round(first_ms, 1),
        "p50": round(statistics.median(times), 1),
        "p95": round(percentile(times, 0.95), 1),
        "min": round(times[0], 1),
        "max": round(times[-1], 1),
        "bytes": len(body),
        "rows": rows_in(body),
        "identical": len(digests) == 1,
    }
    if other_token is not None:
        other_status, other_body, _ = get(target.connect(), path, other_token)
        result["same_for_other_user"] = other_status == status and other_body == body
    return result


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bursts of identical GET requests against the API (read-only).")
    parser.add_argument("paths", nargs="+", help="paths to measure, in order (with their query string)")
    parser.add_argument("--base-url", required=True, help="API base URL, e.g. http://localhost:8100")
    parser.add_argument("-n", type=int, default=50, help="measured requests per path (default 50)")
    parser.add_argument("--warmup", type=int, default=3, help="requests discarded after the first one (default 3)")
    parser.add_argument("--label", default="", help="free text copied to every output line")
    args = parser.parse_args(argv)
    if args.n < 1 or args.warmup < 0:
        parser.error("-n must be at least 1 and --warmup at least 0")
    for path in args.paths:
        if not path.startswith("/"):
            parser.error(f"paths must start with '/': {path!r}")
    return args


def run(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except SystemExit as exit_request:
        # argparse sale con 2; aquí 2 es «la API no responde»: un uso incorrecto es 1.
        return 1 if exit_request.code else 0
    email, password = os.environ.get("BENCH_EMAIL", ""), os.environ.get("BENCH_PASSWORD", "")
    if not email or not password:
        print("error: set BENCH_EMAIL and BENCH_PASSWORD", file=sys.stderr)
        return 1
    try:
        target = parse_target(args.base_url)
        token = login(target, email, password)
        other_email, other_password = os.environ.get("BENCH_OTHER_EMAIL", ""), os.environ.get("BENCH_OTHER_PASSWORD", "")
        other_token = login(target, other_email, other_password) if other_email and other_password else None
        for path in args.paths:
            print(json.dumps(bench(target, path, token, other_token, args.n, args.warmup, args.label)), flush=True)
    except (ValueError, PermissionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: the API is not reachable ({type(error).__name__})", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(run())
