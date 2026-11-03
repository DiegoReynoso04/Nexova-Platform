"""Vocabulario y límites del inventario, compartidos por los modelos ORM y los schemas.

Valores literales de docs/context-nexova-gestion-inventario-hito-5.md. Vive
aparte para que `schemas.py` no importe `models.py`: los schemas de la API y
las tablas no comparten clases, solo este vocabulario.
"""

from enum import StrEnum

# Límite técnico de los textos libres (aprobado por el usuario; no viene del CONTEXT).
TEXT_MAX_LENGTH = 200
# Longitud de un UUID en texto (`str(uuid4())`): el `id` del usuario de TinyDB.
USER_UUID_LENGTH = 36
# Cantidad máxima de una orden: el máximo de INTEGER (int4) en PostgreSQL
# (aprobado por el usuario). Por encima, la base rechazaría el valor con un 500.
QUANTITY_MAX = 2_147_483_647
# Coste unitario de una entrada (P3 del plan de telemetría): NUMERIC(12,2), así
# que como máximo 10 dígitos enteros y 2 decimales.
UNIT_COST_MAX_DIGITS = 12
UNIT_COST_DECIMAL_PLACES = 2


class AssetCategory(StrEnum):
    HARDWARE = "hardware"
    PERIPHERALS = "peripherals"
    OFFICE_SUPPLIES = "office_supplies"
    TRAINING_MATERIALS = "training_materials"


class Office(StrEnum):
    VALENCIA = "Valencia"
    MIAMI = "Miami"


class ExitType(StrEnum):
    ALLOCATION = "allocation"
    CONSUMPTION = "consumption"


class Currency(StrEnum):
    """Moneda de las entradas (P3): la de la oficina, nunca convertida (BRIEFING de telemetría, §6)."""

    EUR = "EUR"
    USD = "USD"


# BRIEFING de telemetría, §6: los montos van en la moneda de la oficina.
OFFICE_CURRENCY = {Office.VALENCIA: Currency.EUR, Office.MIAMI: Currency.USD}
