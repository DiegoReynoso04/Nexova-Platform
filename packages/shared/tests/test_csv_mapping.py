import hashlib
import unittest
from collections import Counter
from datetime import UTC, datetime

from nexova_shared.incident_csv import IncidentFileError
from nexova_shared.incidents import (
    Branch,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    MappingIssue,
    RowIssue,
    SeedIncident,
    derive_title,
    map_csv_row,
    parse_csv_date,
    prepare_seed_batch,
    source_key,
)

from .support import ACCEPTANCE_FIXTURE, HEADER, csv_lines, make_row


def mapped(**overrides: str) -> SeedIncident:
    result = map_csv_row(make_row(**overrides))
    assert isinstance(result, SeedIncident), result
    return result


def issues(**overrides: str) -> frozenset[MappingIssue]:
    result = map_csv_row(make_row(**overrides))
    assert isinstance(result, RowIssue), result
    return result.issues


class TitleTests(unittest.TestCase):
    def test_short_description_is_the_whole_title(self) -> None:
        self.assertEqual(derive_title("Printer not responding"), "Printer not responding")

    def test_title_is_cut_to_120_characters(self) -> None:
        description = "a" * 119 + "bcdefgh"
        title = derive_title(description)
        self.assertEqual(len(title), 120)
        self.assertEqual(title, "a" * 119 + "b")

    def test_exactly_120_characters_is_kept(self) -> None:
        self.assertEqual(derive_title("x" * 120), "x" * 120)

    def test_cut_title_is_trimmed(self) -> None:
        # Si el carácter 120 cae en un espacio, el título no termina en blanco.
        description = "x" * 115 + "     tail of the description"
        self.assertEqual(derive_title(description), "x" * 115)

    def test_description_is_copied_literally(self) -> None:
        description = "y" * 300
        incident = mapped(description=description)
        self.assertEqual(incident.draft.description, description)
        self.assertEqual(incident.draft.title, "y" * 120)

    def test_empty_title_is_discarded(self) -> None:
        self.assertEqual(derive_title(""), "")
        self.assertEqual(issues(description=""), frozenset({MappingIssue.EMPTY_TITLE}))


class DateTests(unittest.TestCase):
    def test_date_is_midnight_utc(self) -> None:
        self.assertEqual(parse_csv_date("2026-08-01"), datetime(2026, 8, 1, tzinfo=UTC))
        self.assertEqual(mapped(date="2026-08-01").created_at, datetime(2026, 8, 1, 0, 0, tzinfo=UTC))

    def test_invalid_dates(self) -> None:
        for raw in ("", "2026-13-01", "2026-02-30", "01/08/2026", "2026/08/01", "20260801", "2026-8-1",
                    "2026-08-01T10:00:00", "2026-W31-6", "２０２６-08-01", "not a date"):
            with self.subTest(raw=raw):
                self.assertIsNone(parse_csv_date(raw))
                self.assertEqual(issues(date=raw), frozenset({MappingIssue.INVALID_DATE}))


class FieldMappingTests(unittest.TestCase):
    def test_status_map(self) -> None:
        expected = {"OPEN": IncidentStatus.OPEN, "CLOSED": IncidentStatus.RESOLVED, "DISCARDED": IncidentStatus.DISCARDED}
        for csv_status, model_status in expected.items():
            with self.subTest(status=csv_status):
                self.assertIs(mapped(status=csv_status, satisfaction_score="4").draft.status, model_status)

    def test_category_map(self) -> None:
        expected = {
            "TECHNICAL": IncidentCategory.TECHNICAL_FAILURE,
            "BILLING": IncidentCategory.PROCESS_ERROR,
            "ACCESS": IncidentCategory.TECHNICAL_FAILURE,
            "HR_QUERY": IncidentCategory.PROCESS_ERROR,
            "COMPLAINT": IncidentCategory.CLIENT_COMPLAINT,
        }
        for csv_category, model_category in expected.items():
            with self.subTest(category=csv_category):
                self.assertIs(mapped(category=csv_category).draft.category, model_category)

    def test_origin_is_always_customer_and_branch_central(self) -> None:
        incident = mapped()
        self.assertIs(incident.draft.origin, IncidentOrigin.CUSTOMER)
        self.assertIs(incident.draft.branch, Branch.CENTRAL)

    def test_status_outside_the_map_is_not_loaded(self) -> None:
        # El analizador no invalida un status desconocido (decisión D3), pero el gestor no lo puede mapear.
        for raw in ("closed", "PENDING", ""):
            with self.subTest(status=raw):
                self.assertEqual(issues(status=raw), frozenset({MappingIssue.UNMAPPED_STATUS}))

    def test_category_outside_the_map_is_not_loaded(self) -> None:
        self.assertEqual(issues(category="SALES"), frozenset({MappingIssue.UNMAPPED_CATEGORY}))

    def test_all_issues_are_reported_together(self) -> None:
        self.assertEqual(
            issues(status="?", category="?", date="?", description=""),
            frozenset(MappingIssue) - {MappingIssue.INVALID_FIELDS},
        )


class SourceKeyTests(unittest.TestCase):
    def test_key_is_the_sha256_of_the_ticket_id(self) -> None:
        # P4-5: el CONTEXT dice que ticket_id no se almacena; solo se guarda su resumen.
        key = mapped(ticket_id="NXV-000042").source_key
        self.assertEqual(key, hashlib.sha256(b"ticket_id:NXV-000042").hexdigest())
        self.assertRegex(key, r"\A[0-9a-f]{64}\Z")
        self.assertNotIn("NXV", key)
        self.assertNotIn("000042", key)

    def test_different_ticket_ids_give_different_keys(self) -> None:
        self.assertNotEqual(mapped(ticket_id="NXV-000001").source_key, mapped(ticket_id="NXV-000002").source_key)

    def test_ticket_id_key_does_not_depend_on_title_or_date(self) -> None:
        first = mapped(ticket_id="NXV-000042", description="Synthetic one", date="2026-08-01")
        second = mapped(ticket_id="NXV-000042", description="Synthetic two", date="2026-08-02")
        self.assertEqual(first.source_key, second.source_key)

    def test_title_and_created_at_when_ticket_id_is_missing(self) -> None:
        created_at = datetime(2026, 8, 1, tzinfo=UTC)
        key = source_key("", "Printer not responding", created_at)
        self.assertEqual(
            key, hashlib.sha256(b"title_created_at:Printer not responding\n2026-08-01T00:00:00+00:00").hexdigest()
        )
        self.assertEqual(key, source_key("", "Printer not responding", created_at))
        self.assertNotEqual(key, source_key("", "Printer not responding", datetime(2026, 8, 2, tzinfo=UTC)))
        self.assertNotEqual(key, source_key("", "Another title", created_at))
        self.assertNotIn("Printer", key)

    def test_fallback_key_from_a_row(self) -> None:
        incident = mapped(ticket_id="", description="Synthetic ticket without id")
        self.assertEqual(
            incident.source_key, source_key("", "Synthetic ticket without id", datetime(2026, 8, 1, tzinfo=UTC))
        )


class SeedBatchTests(unittest.TestCase):
    def test_acceptance_fixture(self) -> None:
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            batch = prepare_seed_batch(stream)
        self.assertEqual(batch.total_rows, 100)
        self.assertEqual(len(batch.incidents), 96)
        self.assertEqual([result.row_number for result in batch.invalid], [18, 45, 71, 93])
        self.assertEqual(
            [sorted(rule.code for rule in result.violations) for result in batch.invalid],
            [["missing_client_company"], ["invalid_category"], ["invalid_email"], ["closed_without_score"]],
        )
        self.assertEqual((batch.unmapped, batch.duplicates), ((), ()))
        self.assertEqual({incident.draft.origin for incident in batch.incidents}, {IncidentOrigin.CUSTOMER})
        self.assertEqual({incident.draft.branch for incident in batch.incidents}, {Branch.CENTRAL})
        self.assertEqual(len({incident.source_key for incident in batch.incidents}), 96)

    def test_every_row_ends_in_exactly_one_list(self) -> None:
        rows = [
            make_row(2, ticket_id="T-1"),
            make_row(3, ticket_id="T-2", client_company=""),  # inválida (regla del analizador)
            make_row(4, ticket_id="T-3", date="yesterday"),  # no mapeable
            make_row(5, ticket_id="T-1"),  # duplicada en el archivo
            make_row(6, ticket_id="", description="Synthetic ticket without id"),
            make_row(7, ticket_id="", description="Synthetic ticket without id"),  # duplicada por title + created_at
            make_row(8, ticket_id="", description="Synthetic ticket without id", date="2026-08-02"),
        ]
        batch = prepare_seed_batch(csv_lines(*rows))
        self.assertEqual(batch.total_rows, 7)
        self.assertEqual([incident.row_number for incident in batch.incidents], [2, 6, 8])
        self.assertEqual([result.row_number for result in batch.invalid], [3])
        self.assertEqual(batch.unmapped, (RowIssue(4, frozenset({MappingIssue.INVALID_DATE})),))
        self.assertEqual(batch.duplicates, (5, 7))

    def test_invalid_rows_take_precedence_over_mapping_issues(self) -> None:
        batch = prepare_seed_batch(csv_lines(make_row(customer_email="", date="bad")))
        self.assertEqual(len(batch.invalid), 1)
        self.assertEqual(batch.unmapped, ())

    def test_header_only(self) -> None:
        batch = prepare_seed_batch([HEADER + "\n"])
        self.assertEqual((batch.total_rows, batch.incidents, batch.invalid), (0, (), ()))

    def test_file_with_the_manager_schema_is_rejected(self) -> None:
        # El esquema del gestor no es el del CSV del analizador.
        lines = ["title,description,category,status,origin,branch\n", "a,b,other,open,internal,central\n"]
        with self.assertRaises(IncidentFileError) as caught:
            prepare_seed_batch(lines)
        self.assertIn("missing required columns", str(caught.exception))

    def test_reports_contain_no_row_values(self) -> None:
        rows = [
            make_row(2, customer_email="leak@example.invalid", description="Hidden description"),
            make_row(3, customer_email="leak@example.invalid", client_company=""),
            make_row(4, customer_email="leak@example.invalid", date="bad"),
        ]
        batch = prepare_seed_batch(csv_lines(*rows))
        texts = [repr(batch.incidents), str(batch.incidents[0]), repr(batch.invalid), repr(batch.unmapped)]
        for text in texts:
            self.assertNotIn("leak", text)
            self.assertNotIn("Hidden", text)

    def test_counts_are_stable(self) -> None:
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            first = prepare_seed_batch(stream)
        with ACCEPTANCE_FIXTURE.open(encoding="utf-8-sig", newline="") as stream:
            second = prepare_seed_batch(stream)
        self.assertEqual([i.source_key for i in first.incidents], [i.source_key for i in second.incidents])
        self.assertEqual(Counter(i.draft.status for i in first.incidents), Counter(i.draft.status for i in second.incidents))


if __name__ == "__main__":
    unittest.main()
