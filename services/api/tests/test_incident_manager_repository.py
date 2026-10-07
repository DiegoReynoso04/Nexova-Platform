"""Repositorio TinyDB del gestor centralizado de incidencias (F2).

Cada test usa su propia base en un directorio temporal: nunca toca
services/api/data/. Datos ficticios.
"""

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from nexova_shared.incidents import (
    Branch,
    FieldErrorCode,
    IncidentCategory,
    IncidentDraft,
    IncidentOrigin,
    IncidentStatus,
    prepare_seed_batch,
    validate_incident_fields,
)

from app.core.config import DEFAULT_INCIDENTS_DB_PATH, SERVICE_ROOT, Settings
from app.modules.incident_manager.repository import (
    INCIDENTS_TABLE,
    SEED_KEYS_TABLE,
    IncidentRepository,
    InvalidStatusTransitionError,
)

from .suppliers_support import FakeClock
from .support import REPO_ROOT

ACCEPTANCE_FIXTURE = (
    REPO_ROOT / "packages" / "incident-analyzer" / "tests" / "fixtures" / "incidents-acceptance-synthetic.csv"
)


def draft(**changes: object) -> IncidentDraft:
    values: dict[str, object] = {
        "title": "Synthetic incident",
        "description": "Synthetic description",
        "category": IncidentCategory.TECHNICAL_FAILURE.value,
        "origin": IncidentOrigin.INTERNAL.value,
        "branch": Branch.CENTRAL.value,
    }
    values.update(changes)
    return validate_incident_fields(values, allowed_statuses=tuple(IncidentStatus))


class RepositoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "nested" / "incidents.json"
        self.clock = FakeClock(datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
        self.repository = IncidentRepository(self.path, clock=self.clock)

    def stored(self) -> dict[str, dict[str, dict[str, object]]]:
        return json.loads(self.path.read_text(encoding="utf-8"))


class EmptyDatabaseTests(RepositoryTestCase):
    def test_reads_without_a_database_file(self) -> None:
        self.assertEqual(self.repository.find(), [])
        self.assertIsNone(self.repository.get(uuid4()))
        self.assertFalse(self.path.exists(), "a read must not create the database")

    def test_summary_without_a_database_is_all_zeros_with_every_key(self) -> None:
        summary = self.repository.summary()
        self.assertEqual(summary.total, 0)
        self.assertEqual(list(summary.by_status), list(IncidentStatus))
        self.assertEqual(list(summary.by_category), list(IncidentCategory))
        self.assertEqual(list(summary.by_origin), list(IncidentOrigin))
        self.assertEqual(list(summary.by_branch), list(Branch))
        for counts in (summary.by_status, summary.by_category, summary.by_origin, summary.by_branch):
            self.assertEqual(set(counts.values()), {0})

    def test_empty_database_file(self) -> None:
        self.path.parent.mkdir(parents=True)
        self.path.write_text("", encoding="utf-8")
        self.assertEqual(self.repository.find(), [])
        self.assertEqual(self.repository.summary().total, 0)

    def test_summary_json_has_every_key(self) -> None:
        dumped = self.repository.summary().model_dump(mode="json")
        self.assertEqual(dumped["by_status"], {status.value: 0 for status in IncidentStatus})
        self.assertEqual(dumped["by_branch"], {branch.value: 0 for branch in Branch})

    def test_change_status_of_a_missing_incident(self) -> None:
        self.assertIsNone(self.repository.change_status(uuid4(), IncidentStatus.IN_PROGRESS))


class CreateTests(RepositoryTestCase):
    def test_create_generates_id_and_utc_timestamps(self) -> None:
        incident = self.repository.create(draft())
        self.assertIsInstance(incident.id, UUID)
        self.assertEqual(incident.id.version, 4)
        self.assertEqual(incident.created_at, datetime(2026, 10, 7, 9, 0, tzinfo=UTC))
        self.assertEqual(incident.updated_at, incident.created_at)
        self.assertEqual(incident.created_at.utcoffset().total_seconds(), 0)
        self.assertEqual(self.repository.get(incident.id), incident)

    def test_ids_are_unique(self) -> None:
        ids = {self.repository.create(draft()).id for _ in range(5)}
        self.assertEqual(len(ids), 5)

    def test_stored_document(self) -> None:
        incident = self.repository.create(draft(origin="branch", branch="miami_office", category="sla_breach"))
        (document,) = self.stored()[INCIDENTS_TABLE].values()
        self.assertEqual(
            document,
            {
                "id": str(incident.id),
                "title": "Synthetic incident",
                "description": "Synthetic description",
                "category": "sla_breach",
                "status": "open",
                "origin": "branch",
                "branch": "miami_office",
                "created_at": "2026-10-07T09:00:00Z",
                "updated_at": "2026-10-07T09:00:00Z",
            },
        )

    def test_persists_between_repository_instances(self) -> None:
        incident = self.repository.create(draft())
        self.assertEqual(IncidentRepository(self.path).get(incident.id), incident)


class FindTests(RepositoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        rows = [
            ("open", "customer", "central", "client_complaint"),
            ("in_progress", "branch", "miami_office", "technical_failure"),
            ("resolved", "branch", "remote", "technical_failure"),
            ("discarded", "internal", "valencia_operations", "sla_breach"),
            ("open", "branch", "miami_office", "sla_breach"),
        ]
        self.created = []
        for status, origin, branch, category in rows:
            self.clock.advance(minutes=1)
            self.created.append(
                self.repository.create(draft(status=status, origin=origin, branch=branch, category=category))
            )

    def test_without_filters_returns_everything_newest_first(self) -> None:
        self.assertEqual(self.repository.find(), list(reversed(self.created)))

    def test_each_filter(self) -> None:
        self.assertEqual(len(self.repository.find(status=IncidentStatus.OPEN)), 2)
        self.assertEqual(len(self.repository.find(origin=IncidentOrigin.BRANCH)), 3)
        self.assertEqual(len(self.repository.find(branch=Branch.MIAMI_OFFICE)), 2)
        self.assertEqual(len(self.repository.find(category=IncidentCategory.SLA_BREACH)), 2)

    def test_filters_are_combined_with_and(self) -> None:
        found = self.repository.find(origin=IncidentOrigin.BRANCH, branch=Branch.MIAMI_OFFICE, status=IncidentStatus.OPEN)
        self.assertEqual(found, [self.created[4]])
        both = self.repository.find(category=IncidentCategory.TECHNICAL_FAILURE, origin=IncidentOrigin.BRANCH)
        self.assertEqual(both, [self.created[2], self.created[1]])

    def test_filter_without_matches(self) -> None:
        self.assertEqual(self.repository.find(category=IncidentCategory.DATA_QUALITY), [])

    def test_summary(self) -> None:
        summary = self.repository.summary()
        self.assertEqual(summary.total, 5)
        self.assertEqual(
            summary.by_status,
            {IncidentStatus.OPEN: 2, IncidentStatus.IN_PROGRESS: 1, IncidentStatus.RESOLVED: 1, IncidentStatus.DISCARDED: 1},
        )
        self.assertEqual(summary.by_origin[IncidentOrigin.BRANCH], 3)
        self.assertEqual(summary.by_branch[Branch.CENTRAL], 1)
        self.assertEqual(summary.by_category[IncidentCategory.OTHER], 0)
        self.assertEqual(sum(summary.by_category.values()), 5)


class ChangeStatusTests(RepositoryTestCase):
    def test_valid_transitions_update_updated_at_only(self) -> None:
        incident = self.repository.create(draft())
        self.clock.advance(hours=1)
        in_progress = self.repository.change_status(incident.id, IncidentStatus.IN_PROGRESS)
        assert in_progress is not None
        self.assertEqual(in_progress.status, IncidentStatus.IN_PROGRESS)
        self.assertEqual(in_progress.created_at, incident.created_at)
        self.assertEqual(in_progress.updated_at, datetime(2026, 10, 7, 10, 0, tzinfo=UTC))
        self.assertEqual(in_progress.model_dump(exclude={"status", "updated_at"}), incident.model_dump(exclude={"status", "updated_at"}))

        self.clock.advance(hours=1)
        resolved = self.repository.change_status(incident.id, IncidentStatus.RESOLVED)
        assert resolved is not None
        self.assertEqual(self.repository.get(incident.id), resolved)
        self.assertEqual(resolved.updated_at, datetime(2026, 10, 7, 11, 0, tzinfo=UTC))

    def test_invalid_transition_changes_nothing(self) -> None:
        incident = self.repository.create(draft())
        before = self.path.read_bytes()
        self.clock.advance(hours=1)
        with self.assertRaises(InvalidStatusTransitionError) as caught:
            self.repository.change_status(incident.id, IncidentStatus.RESOLVED)
        self.assertEqual(caught.exception.error.field, "status")
        self.assertEqual(caught.exception.error.error, FieldErrorCode.INVALID_TRANSITION)
        self.assertEqual(self.repository.get(incident.id), incident)
        self.assertEqual(self.path.read_bytes(), before)

    def test_final_statuses_cannot_change(self) -> None:
        for final in (IncidentStatus.RESOLVED, IncidentStatus.DISCARDED):
            incident = self.repository.create(draft(status=final.value))
            for target in IncidentStatus:
                with self.subTest(final=final.value, target=target.value), self.assertRaises(InvalidStatusTransitionError):
                    self.repository.change_status(incident.id, target)

    def test_only_the_target_incident_changes(self) -> None:
        first = self.repository.create(draft())
        second = self.repository.create(draft())
        self.repository.change_status(first.id, IncidentStatus.DISCARDED)
        self.assertEqual(self.repository.get(second.id), second)


class SeedTests(RepositoryTestCase):
    def batch(self):  # type: ignore[no-untyped-def]
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            return prepare_seed_batch(stream)

    def test_seed_is_idempotent(self) -> None:
        first = self.repository.seed(self.batch().incidents)
        self.assertEqual((first.inserted, first.existing, first.total), (96, 0, 96))
        second = self.repository.seed(self.batch().incidents)
        self.assertEqual((second.inserted, second.existing, second.total), (0, 96, 96))
        self.assertEqual(len(self.stored()[SEED_KEYS_TABLE]), 96)

    def test_seeded_incidents_keep_the_csv_date(self) -> None:
        self.repository.seed(self.batch().incidents)
        for incident in self.repository.find():
            self.assertEqual(incident.updated_at, incident.created_at)
            self.assertEqual((incident.created_at.hour, incident.created_at.minute), (0, 0))
            self.assertEqual(incident.created_at.tzinfo, UTC)

    def test_seed_totals_match_the_context(self) -> None:
        self.repository.seed(self.batch().incidents)
        summary = self.repository.summary()
        self.assertEqual(summary.total, 96)
        self.assertEqual(
            summary.by_status,
            {IncidentStatus.OPEN: 27, IncidentStatus.IN_PROGRESS: 0, IncidentStatus.RESOLVED: 56, IncidentStatus.DISCARDED: 13},
        )
        expected_categories = {category: 0 for category in IncidentCategory}
        expected_categories.update(
            {IncidentCategory.TECHNICAL_FAILURE: 49, IncidentCategory.PROCESS_ERROR: 35, IncidentCategory.CLIENT_COMPLAINT: 12}
        )
        self.assertEqual(summary.by_category, expected_categories)
        self.assertEqual(summary.by_origin, {IncidentOrigin.CUSTOMER: 96, IncidentOrigin.BRANCH: 0, IncidentOrigin.INTERNAL: 0})
        self.assertEqual(summary.by_branch[Branch.CENTRAL], 96)

    def test_seed_keys_store_only_the_sha256(self) -> None:
        self.repository.seed(self.batch().incidents)
        incident_ids = {str(incident.id) for incident in self.repository.find()}
        for document in self.stored()[SEED_KEYS_TABLE].values():
            self.assertEqual(set(document), {"key_sha256", "incident_id"})
            self.assertRegex(str(document["key_sha256"]), r"\A[0-9a-f]{64}\Z")
            self.assertIn(document["incident_id"], incident_ids)
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("NXV-", raw)
        self.assertNotIn("ticket_id", raw)
        self.assertNotIn("@", raw)

    def test_incidents_created_by_the_api_are_not_touched_by_the_seed(self) -> None:
        manual = self.repository.create(draft())
        result = self.repository.seed(self.batch().incidents)
        self.assertEqual((result.inserted, result.total), (96, 97))
        self.assertEqual(self.repository.get(manual.id), manual)

    def test_status_changes_survive_a_second_seed(self) -> None:
        self.repository.seed(self.batch().incidents)
        target = self.repository.find(status=IncidentStatus.OPEN)[0]
        self.repository.change_status(target.id, IncidentStatus.IN_PROGRESS)
        self.repository.seed(self.batch().incidents)
        self.assertEqual(self.repository.summary().by_status[IncidentStatus.IN_PROGRESS], 1)


class ConfigTests(unittest.TestCase):
    def test_default_path_is_inside_the_ignored_data_folder(self) -> None:
        self.assertEqual(DEFAULT_INCIDENTS_DB_PATH, SERVICE_ROOT / "data" / "incidents.json")
        self.assertEqual(Settings.from_env({}).incidents_db_path, DEFAULT_INCIDENTS_DB_PATH)

    def test_path_from_environment(self) -> None:
        settings = Settings.from_env({"INCIDENTS_DB_PATH": " C:/tmp/incidents.json "})
        self.assertEqual(settings.incidents_db_path, Path("C:/tmp/incidents.json"))


if __name__ == "__main__":
    unittest.main()
