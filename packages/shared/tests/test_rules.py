import itertools
import unittest

from nexova_shared.incidents import (
    INPUT_FIELDS,
    Branch,
    FieldErrorCode,
    IncidentCategory,
    IncidentOrigin,
    IncidentStatus,
    IncidentValidationError,
    can_transition,
    check_transition,
    validate_incident_fields,
)

OPEN = IncidentStatus.OPEN
IN_PROGRESS = IncidentStatus.IN_PROGRESS
RESOLVED = IncidentStatus.RESOLVED
DISCARDED = IncidentStatus.DISCARDED

# Las 16 combinaciones (origen, destino) y si están permitidas, escritas a mano
# a partir del CONTEXT (no derivadas de ALLOWED_TRANSITIONS).
TRANSITIONS = {
    (OPEN, OPEN): False,
    (OPEN, IN_PROGRESS): True,
    (OPEN, RESOLVED): False,
    (OPEN, DISCARDED): True,
    (IN_PROGRESS, OPEN): False,
    (IN_PROGRESS, IN_PROGRESS): False,
    (IN_PROGRESS, RESOLVED): True,
    (IN_PROGRESS, DISCARDED): True,
    (RESOLVED, OPEN): False,
    (RESOLVED, IN_PROGRESS): False,
    (RESOLVED, RESOLVED): False,
    (RESOLVED, DISCARDED): False,
    (DISCARDED, OPEN): False,
    (DISCARDED, IN_PROGRESS): False,
    (DISCARDED, RESOLVED): False,
    (DISCARDED, DISCARDED): False,
}


def valid_input(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "title": "Synthetic incident",
        "description": "Synthetic description of the incident",
        "category": "technical_failure",
        "origin": "internal",
        "branch": "central",
    }
    values.update(overrides)
    return values


class TransitionTests(unittest.TestCase):
    def test_table_covers_all_16_combinations(self) -> None:
        self.assertEqual(set(TRANSITIONS), set(itertools.product(IncidentStatus, repeat=2)))
        self.assertEqual(len(TRANSITIONS), 16)

    def test_every_combination(self) -> None:
        for (current, target), allowed in TRANSITIONS.items():
            with self.subTest(current=current.value, target=target.value):
                self.assertIs(can_transition(current, target), allowed)
                error = check_transition(current, target)
                if allowed:
                    self.assertIsNone(error)
                else:
                    assert error is not None
                    self.assertEqual(error.field, "status")
                    self.assertEqual(error.error, FieldErrorCode.INVALID_TRANSITION)

    def test_messages_explain_the_lifecycle(self) -> None:
        final = check_transition(RESOLVED, OPEN)
        assert final is not None
        self.assertEqual(final.message, "status resolved is final and cannot change")
        not_allowed = check_transition(OPEN, RESOLVED)
        assert not_allowed is not None
        self.assertEqual(not_allowed.message, "status open can only change to: discarded, in_progress")


class ValidIncidentTests(unittest.TestCase):
    def test_valid_input_returns_a_normalized_draft(self) -> None:
        draft = validate_incident_fields(valid_input(title="  Synthetic incident  ", description="\tText\n"))
        self.assertEqual(draft.title, "Synthetic incident")
        self.assertEqual(draft.description, "Text")
        self.assertIs(draft.category, IncidentCategory.TECHNICAL_FAILURE)
        self.assertIs(draft.origin, IncidentOrigin.INTERNAL)
        self.assertIs(draft.branch, Branch.CENTRAL)

    def test_status_defaults_to_open(self) -> None:
        self.assertIs(validate_incident_fields(valid_input()).status, OPEN)
        self.assertIs(validate_incident_fields(valid_input(status=None)).status, OPEN)
        self.assertIs(validate_incident_fields(valid_input(status="open")).status, OPEN)

    def test_creation_only_allows_open_by_default(self) -> None:
        for status in ("in_progress", "resolved", "discarded"):
            with self.subTest(status=status), self.assertRaises(IncidentValidationError) as caught:
                validate_incident_fields(valid_input(status=status))
            (error,) = caught.exception.errors
            self.assertEqual((error.field, error.error), ("status", FieldErrorCode.INVALID_CHOICE))
            self.assertEqual(error.message, "status must be one of: open")

    def test_seed_can_allow_every_status(self) -> None:
        for status in IncidentStatus:
            with self.subTest(status=status.value):
                draft = validate_incident_fields(valid_input(status=status.value), allowed_statuses=tuple(IncidentStatus))
                self.assertIs(draft.status, status)

    def test_branch_is_required_for_every_origin(self) -> None:
        for origin in IncidentOrigin:
            with self.subTest(origin=origin.value), self.assertRaises(IncidentValidationError) as caught:
                validate_incident_fields(valid_input(origin=origin.value, branch=None))
            self.assertEqual([(e.field, e.error) for e in caught.exception.errors], [("branch", FieldErrorCode.MISSING)])

    def test_every_branch_category_and_origin_is_accepted(self) -> None:
        for branch, category, origin in itertools.product(Branch, IncidentCategory, IncidentOrigin):
            draft = validate_incident_fields(valid_input(branch=branch.value, category=category.value, origin=origin.value))
            self.assertEqual((draft.branch, draft.category, draft.origin), (branch, category, origin))

    def test_title_of_exactly_120_characters_is_accepted(self) -> None:
        self.assertEqual(len(validate_incident_fields(valid_input(title="x" * 120)).title), 120)

    def test_description_has_no_maximum(self) -> None:
        self.assertEqual(len(validate_incident_fields(valid_input(description="x" * 100_000)).description), 100_000)


class InvalidIncidentTests(unittest.TestCase):
    def assertSingleError(self, raw: dict[str, object], field: str, code: FieldErrorCode) -> str:
        with self.assertRaises(IncidentValidationError) as caught:
            validate_incident_fields(raw)
        self.assertEqual([(e.field, e.error) for e in caught.exception.errors], [(field, code)])
        return caught.exception.errors[0].message

    def test_each_required_field_missing(self) -> None:
        for field in ("title", "description", "category", "origin", "branch"):
            with self.subTest(field=field):
                raw = valid_input()
                del raw[field]
                message = self.assertSingleError(raw, field, FieldErrorCode.MISSING)
                self.assertEqual(message, f"{field} is required")

    def test_blank_text(self) -> None:
        for field in ("title", "description"):
            with self.subTest(field=field):
                self.assertSingleError(valid_input(**{field: "   "}), field, FieldErrorCode.BLANK)

    def test_title_longer_than_120_characters(self) -> None:
        message = self.assertSingleError(valid_input(title="x" * 121), "title", FieldErrorCode.TOO_LONG)
        self.assertEqual(message, "title must be at most 120 characters")

    def test_length_is_checked_after_trimming(self) -> None:
        self.assertEqual(validate_incident_fields(valid_input(title=" " + "x" * 120 + " ")).title, "x" * 120)

    def test_text_must_be_a_string(self) -> None:
        self.assertSingleError(valid_input(title=42), "title", FieldErrorCode.INVALID_TYPE)

    def test_values_outside_the_context(self) -> None:
        cases = {
            "category": ("TECHNICAL", "Technical_Failure", " technical_failure", "headquarters", 1),
            "origin": ("Customer", "client", True),
            "branch": ("headquarters", "valencia", "Central", "miami"),
            "status": ("closed", "OPEN", 0),
        }
        for field, bad_values in cases.items():
            for bad in bad_values:
                with self.subTest(field=field, value=bad):
                    self.assertSingleError(valid_input(**{field: bad}), field, FieldErrorCode.INVALID_CHOICE)

    def test_invalid_choice_message_lists_the_allowed_values(self) -> None:
        message = self.assertSingleError(valid_input(branch="headquarters"), "branch", FieldErrorCode.INVALID_CHOICE)
        self.assertEqual(message, "branch must be one of: central, valencia_operations, miami_office, remote")

    def test_system_fields_are_rejected(self) -> None:
        for field in ("id", "created_at", "updated_at"):
            with self.subTest(field=field):
                self.assertSingleError(valid_input(**{field: "x"}), field, FieldErrorCode.UNKNOWN_FIELD)

    def test_reports_every_error_in_field_order(self) -> None:
        with self.assertRaises(IncidentValidationError) as caught:
            validate_incident_fields({"zzz": 1, "branch": "nowhere", "title": ""})
        self.assertEqual(
            [error.field for error in caught.exception.errors],
            [*INPUT_FIELDS[:3], *INPUT_FIELDS[4:], "zzz"],
        )
        self.assertEqual(str(caught.exception), "invalid incident fields: title, description, category, origin, branch, zzz")

    def test_messages_never_echo_the_value(self) -> None:
        secret = "leak@example.invalid"
        raw = valid_input(category=secret, origin=secret, branch=secret, status=secret, title=secret * 10)
        with self.assertRaises(IncidentValidationError) as caught:
            validate_incident_fields(raw)
        for error in caught.exception.errors:
            self.assertNotIn("leak", error.message)
        self.assertNotIn("leak", str(caught.exception))

    def test_draft_repr_hides_values(self) -> None:
        draft = validate_incident_fields(valid_input(description="Hidden customer detail"))
        for text in (repr(draft), str(draft), repr([draft])):
            self.assertNotIn("Hidden", text)


if __name__ == "__main__":
    unittest.main()
