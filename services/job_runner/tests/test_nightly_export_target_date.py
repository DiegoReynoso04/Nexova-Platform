import unittest
from datetime import UTC, date, datetime

from .support import load_script

script = load_script()
NOW = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)  # lunes


class TargetDateTests(unittest.TestCase):
    def test_default_is_yesterday_in_utc(self):
        for raw in (None, "", "   "):
            self.assertEqual(script.resolve_target_date(raw, NOW), date(2026, 11, 15))

    def test_default_uses_the_utc_day_not_the_local_one(self):
        late = datetime(2026, 11, 15, 23, 30, tzinfo=UTC)
        self.assertEqual(script.resolve_target_date(None, late), date(2026, 11, 14))

    def test_a_valid_closed_day(self):
        self.assertEqual(script.resolve_target_date("2026-10-27", NOW), date(2026, 10, 27))
        self.assertEqual(script.resolve_target_date(" 2026-11-15 ", NOW), date(2026, 11, 15))

    def test_wrong_formats_are_rejected_even_if_fromisoformat_accepts_them(self):
        for raw in ("20261015", "2026-W44-1", "2026-10-5", "15-10-2026", "2026/10/15", "yesterday", "2026-10-15T00:00"):
            with self.subTest(raw=raw), self.assertRaisesRegex(script.TargetDateError, "format YYYY-MM-DD"):
                script.resolve_target_date(raw, NOW)

    def test_impossible_dates(self):
        for raw in ("2026-13-01", "2026-02-30", "2026-00-10"):
            with self.subTest(raw=raw), self.assertRaisesRegex(script.TargetDateError, "valid calendar date"):
                script.resolve_target_date(raw, NOW)

    def test_today_and_future_are_rejected(self):
        for raw in ("2026-11-16", "2026-11-17", "2030-01-01"):
            with self.subTest(raw=raw), self.assertRaisesRegex(script.TargetDateError, "closed day"):
                script.resolve_target_date(raw, NOW)

    def test_retention_limit(self):
        # Semana del 2026-08-24 = hoy − 84 días: la última permitida; la anterior, no.
        self.assertEqual(script.resolve_target_date("2026-08-24", NOW), date(2026, 8, 24))
        with self.assertRaisesRegex(script.TargetDateError, "retention"):
            script.resolve_target_date("2026-08-23", NOW)

    def test_messages_never_repeat_the_value(self):
        for raw in ("garbage-value", "2026-02-30", "2099-01-01", "2020-01-01"):
            with self.assertRaises(script.TargetDateError) as caught:
                script.resolve_target_date(raw, NOW)
            self.assertNotIn(raw, str(caught.exception))


class PipelineWeekTests(unittest.TestCase):
    def test_sunday_closes_its_week(self):
        self.assertEqual(script.pipeline_week(date(2026, 11, 15), NOW), date(2026, 11, 9))

    def test_a_day_of_the_current_week_falls_back_to_the_last_closed_week(self):
        tuesday_night = datetime(2026, 11, 17, 2, 0, tzinfo=UTC)
        self.assertEqual(script.pipeline_week(date(2026, 11, 16), tuesday_night), date(2026, 11, 9))

    def test_an_old_day_recalculates_its_own_week(self):
        self.assertEqual(script.pipeline_week(date(2026, 10, 27), NOW), date(2026, 10, 26))
        self.assertEqual(script.pipeline_week(date(2026, 10, 25), NOW), date(2026, 10, 19))
