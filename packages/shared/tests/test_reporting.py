"""Vocabulario del esquema `reporting`: coherente con el contrato de eventos y con el diseño."""

import json
import unittest

from nexova_shared.reporting import (
    BUSINESS_EVENT_TYPES,
    OFFICE_CURRENCY,
    PROGRAMME_SLUG_PATTERN,
    RETENTION_GUARD_DAYS,
    UNASSIGNED_PROGRAMME,
    Currency,
    Office,
    RunPhase,
    RunStatus,
    RunTrigger,
)

from .support import REPO_ROOT

SCHEMAS = REPO_ROOT / "docs" / "telemetry" / "event-schemas.json"
DESIGN = REPO_ROOT / "data" / "pipelines" / "PIPELINE_DESIGN.md"


class ReportingVocabularyTests(unittest.TestCase):
    def test_sentinel_never_matches_a_programme_slug(self):
        self.assertIsNone(PROGRAMME_SLUG_PATTERN.fullmatch(UNASSIGNED_PROGRAMME))
        self.assertIsNotNone(PROGRAMME_SLUG_PATTERN.fullmatch("programa-ficticio"))

    def test_each_office_has_its_own_currency(self):
        self.assertEqual(OFFICE_CURRENCY, {Office.VALENCIA: Currency.EUR, Office.MIAMI: Currency.USD})

    def test_business_events_exist_in_the_event_contract(self):
        text = SCHEMAS.read_text(encoding="utf-8")
        json.loads(text)  # el contrato es JSON válido
        for event_type in BUSINESS_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertIn(f'"{event_type}"', text)

    def test_status_phase_and_trigger_match_the_design_checks(self):
        design = DESIGN.read_text(encoding="utf-8")
        self.assertIn("check (trigger in ('schedule', 'manual', 'backfill'))", design)
        self.assertEqual({member.value for member in RunTrigger}, {"schedule", "manual", "backfill"})
        self.assertEqual({member.value for member in RunStatus}, {"running", "completed", "failed"})
        self.assertEqual([member.value for member in RunPhase], ["extract", "transform", "load", "done"])

    def test_retention_guard_is_the_one_of_the_design(self):
        # §3.4: «now() - 84 días», dentro de los 90 de retención de los eventos en bruto.
        self.assertIn("now() - 84 días", DESIGN.read_text(encoding="utf-8"))
        self.assertEqual(RETENTION_GUARD_DAYS, 84)


if __name__ == "__main__":
    unittest.main()
