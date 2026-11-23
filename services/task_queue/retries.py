"""Backoff exponencial con jitter acotado (A8-B), nunca inmediato.

Celery tiene su propio `retry_backoff` con `retry_jitter`, pero su jitter elige al
azar entre 0 y la cuenta atrás (`get_exponential_backoff_interval`, `full_jitter`:
`random.randrange(countdown + 1)`), así que un reintento puede salir con 0 s. Aquí el
jitter solo suma: el mínimo es siempre `base · 2^n`.
"""

from __future__ import annotations

import random
from collections.abc import Callable

from .config import BACKOFF_BASE_SECONDS, BACKOFF_MAX_SECONDS


def backoff_floor(retries: int, *, base: float = BACKOFF_BASE_SECONDS, maximum: float = BACKOFF_MAX_SECONDS) -> float:
    """El mínimo de la cuenta atrás tras `retries` reintentos ya hechos: `base · 2^n`, con tope."""
    if retries < 0:
        raise ValueError("retries must be >= 0")
    return min(maximum, base * (2**retries))


def backoff_countdown(
    retries: int,
    *,
    base: float = BACKOFF_BASE_SECONDS,
    maximum: float = BACKOFF_MAX_SECONDS,
    rng: Callable[[], float] = random.random,
) -> float:
    """Segundos hasta el siguiente intento: `base · 2^n + uniforme(0, base)`.

    Con base 2: 2–4 s, 4–6 s y 8–10 s para los reintentos 1, 2 y 3.
    """
    return backoff_floor(retries, base=base, maximum=maximum) + rng() * base
