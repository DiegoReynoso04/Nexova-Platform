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
