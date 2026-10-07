"""Contrato: enumerados, etiquetas, ciclo de vida y mapeos contra docs/centralized-incident-manager.md.

Lee el propio CONTEXT: si alguien cambia un valor en el código o en el
documento sin cambiar el otro, estos tests fallan.
"""

import re
import unittest
from collections import Counter

from nexova_shared.incident_csv import Category, Status
from nexova_shared.incidents import (
    ALLOWED_TRANSITIONS,
    BRANCH_LABELS,
    CATEGORY_MAP,
    FINAL_STATUSES,
    INITIAL_STATUS,
    SEED_BRANCH,
    SEED_ORIGIN,
    STATUS_MAP,
    TITLE_MAX_LENGTH,
    Branch,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    prepare_seed_batch,
)

from .support import ACCEPTANCE_FIXTURE, context_table, context_text, context_values


def values(enum: type) -> list[str]:
    return [member.value for member in enum]


class VocabularyContractTests(unittest.TestCase):
    def test_branches_and_display_names(self) -> None:
        table = context_table("## Oficinas de Nexova")
        self.assertEqual(values(Branch), [row[0] for row in table])
        self.assertEqual({branch.value: label for branch, label in BRANCH_LABELS.items()}, dict(table))

    def test_every_branch_has_a_label(self) -> None:
        self.assertEqual(set(BRANCH_LABELS), set(Branch))

    def test_categories(self) -> None:
        self.assertEqual(values(IncidentCategory), context_values("## Categorías de incidencias"))

    def test_statuses(self) -> None:
        self.assertEqual(values(IncidentStatus), context_values("## Estados y ciclo de vida"))

    def test_origins(self) -> None:
        self.assertEqual(values(IncidentOrigin), context_values("## Orígenes"))

    def test_sla_breach_is_a_plain_category(self) -> None:
        # "diseña el modelo pensando en que ese filtro debe ser trivial de añadir".
        self.assertIn("sla_breach", values(IncidentCategory))


class LifecycleContractTests(unittest.TestCase):
    def test_transitions(self) -> None:
        line = next(line for line in context_text().splitlines() if line.startswith("Transiciones válidas:"))
        documented = set(re.findall(r"`(\w+) → (\w+)`", line))
        self.assertEqual(len(documented), 4)
        implemented = {(source.value, target.value) for source, targets in ALLOWED_TRANSITIONS.items() for target in targets}
        self.assertEqual(implemented, documented)

    def test_final_statuses(self) -> None:
        line = next(line for line in context_text().splitlines() if line.startswith("Transiciones válidas:"))
        finals = re.search(r"Los estados `(\w+)` y `(\w+)` son finales", line)
        assert finals is not None
        self.assertEqual({status.value for status in FINAL_STATUSES}, set(finals.groups()))

    def test_initial_status_is_open(self) -> None:
        self.assertEqual(INITIAL_STATUS, IncidentStatus.OPEN)


class MappingContractTests(unittest.TestCase):
    def test_status_map(self) -> None:
        documented = dict(context_table("### Mapeo de estados"))
        self.assertEqual({source.value: target.value for source, target in STATUS_MAP.items()}, documented)

    def test_status_map_covers_every_csv_status(self) -> None:
        self.assertEqual(set(STATUS_MAP), set(Status))

    def test_category_map(self) -> None:
        documented = dict(context_table("### Mapeo de categorías (Nexova)"))
        self.assertEqual({source.value: target.value for source, target in CATEGORY_MAP.items()}, documented)

    def test_category_map_covers_every_csv_category(self) -> None:
        self.assertEqual(set(CATEGORY_MAP), set(Category))

    def test_direct_field_mapping(self) -> None:
        rows = {row[1]: row[2] for row in context_table("### Mapeo directo de campos")}
        self.assertIn(f'"{SEED_ORIGIN.value}"', rows["origin"])
        self.assertIn(f'"{SEED_BRANCH.value}"', rows["branch"])
        title_rule = re.search(r"Primeros (\d+) caracteres", rows["title"])
        assert title_rule is not None
        self.assertEqual(int(title_rule.group(1)), TITLE_MAX_LENGTH)
        self.assertIn("medianoche UTC", rows["created_at"])

    def test_idempotency_key_is_ticket_id(self) -> None:
        self.assertIn("usa `ticket_id` del CSV", context_text())
        self.assertIn("la combinación `title + created_at`", context_text())


class ExpectedSeedValuesTests(unittest.TestCase):
    """"Valores esperados tras el seed", con el fixture sintético de aceptación del analizador.

    El fixture reproduce las cifras del dataset real (100 filas, 96 válidas); el
    CSV real no está en el repositorio.
    """

    @classmethod
    def setUpClass(cls) -> None:
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            cls.batch = prepare_seed_batch(stream)

    def expected(self, marker: str) -> dict[str, int]:
        return {name: int(count) for name, count in context_table(marker)}

    def test_status_totals(self) -> None:
        totals = Counter(incident.draft.status.value for incident in self.batch.incidents)
        self.assertEqual(dict(totals), self.expected("**Por `status` del modelo:**"))

    def test_category_totals(self) -> None:
        totals = Counter(incident.draft.category.value for incident in self.batch.incidents)
        self.assertEqual(dict(totals), self.expected("**Por `category` del modelo:**"))

    def test_96_valid_records(self) -> None:
        self.assertIn("**96 registros válidos**", context_text())
        self.assertEqual(len(self.batch.incidents), 96)
        self.assertEqual(sum(self.expected("**Por `status` del modelo:**").values()), 96)


if __name__ == "__main__":
    unittest.main()
