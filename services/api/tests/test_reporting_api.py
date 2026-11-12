"""`/reporting` (services/reporting): contrato, auth y códigos de §5 del diseño. Datos ficticios."""

import unittest
from datetime import UTC, datetime, timedelta
from unittest import mock
from uuid import uuid4

from business_performance.trigger import PipelineUnavailableError, RunAlreadyActiveError, TriggeredRun

from app.auth.models import UserRole
from app.core.config import Settings

from .reporting_support import FAKE_PREFECT_URL, add_row, add_run, attach_reporting, closed_week
from .support import authorize, make_client

WEEKLY_URL = "/reporting/weekly-office-program-performance"
LATEST_URL = "/reporting/pipeline-runs/latest"
RUNS_URL = "/reporting/pipeline-runs"
ENTRY_KEYS = {
    "office", "programme_id", "total_material_cost", "kits_delivered_count",
    "shortage_events_count", "cost_variance_events_count", "currency",
}


def _client(role: UserRole = UserRole.USER, *, prefect_url: str = FAKE_PREFECT_URL, tables: bool = True):
    client = make_client(Settings(pipeline_prefect_api_url=prefect_url), authenticated=False)
    attach_reporting(client, tables=tables)
    user = authorize(client, role)
    return client, user


class WeeklyPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.client, _ = _client()
        self.week = closed_week()
        run = add_run(self.client, week_from=closed_week(1), week_to=self.week)
        add_row(self.client, run, self.week, "valencia", "147.05", kits=1)
        add_row(self.client, run, self.week, "miami", "0", kits=2, shortage=1)
        add_row(self.client, run, closed_week(1), "miami", "49.95", kits=2)

    def test_briefing_contract_ordered_by_office_and_programme(self):
        response = self.client.get(WEEKLY_URL, params={"week_start": self.week.isoformat()})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"week_start", "entries"})
        self.assertEqual(body["week_start"], self.week.isoformat())
        self.assertEqual([entry["office"] for entry in body["entries"]], ["miami", "valencia"])
        for entry in body["entries"]:
            with self.subTest(office=entry["office"]):
                self.assertEqual(set(entry), ENTRY_KEYS)
        valencia = body["entries"][1]
        self.assertEqual(valencia, {
            "office": "valencia", "programme_id": "_unassigned", "total_material_cost": 147.05,
            "kits_delivered_count": 1, "shortage_events_count": 0, "cost_variance_events_count": 0,
            "currency": "EUR"})
        self.assertIsInstance(valencia["total_material_cost"], float)  # número JSON, no texto

    def test_default_is_the_latest_computed_week(self):
        response = self.client.get(WEEKLY_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["week_start"], self.week.isoformat())

    def test_computed_week_without_activity_has_no_entries(self):
        empty = closed_week(3)
        add_run(self.client, week_from=empty)
        response = self.client.get(WEEKLY_URL, params={"week_start": empty.isoformat()})
        self.assertEqual((response.status_code, response.json()["entries"]), (200, []))

    def test_week_not_computed_is_404(self):
        for week in (closed_week(5), closed_week() + timedelta(weeks=1)):
            with self.subTest(week=week):
                response = self.client.get(WEEKLY_URL, params={"week_start": week.isoformat()})
                self.assertEqual((response.status_code, response.json()["code"]), (404, "week_not_computed"))

    def test_failed_run_does_not_count_as_computed(self):
        failed_week = closed_week(4)
        add_run(self.client, week_from=failed_week, status="failed")
        response = self.client.get(WEEKLY_URL, params={"week_start": failed_week.isoformat()})
        self.assertEqual(response.status_code, 404)

    def test_not_a_monday_or_not_a_date_is_422(self):
        for value in ((self.week + timedelta(days=1)).isoformat(), "x"):
            with self.subTest(value=value):
                response = self.client.get(WEEKLY_URL, params={"week_start": value})
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))

    def test_without_token_is_401(self):
        self.client.headers.pop("Authorization")
        self.assertEqual(self.client.get(WEEKLY_URL).status_code, 401)

    def test_no_run_at_all_is_404(self):
        client, _ = _client()
        self.assertEqual(client.get(WEEKLY_URL).json()["code"], "week_not_computed")


class LatestRunTests(unittest.TestCase):
    def test_latest_by_start_without_requested_by(self):
        client, _ = _client()
        add_run(client, week_from=closed_week(1), started_at=datetime.now(UTC) - timedelta(hours=1))
        latest = add_run(client, week_from=closed_week(), requested_by=uuid4(),
                         quality={"optional_steps": {"eval_snapshot": "failed", "error_class": "OSError"}})
        response = client.get(LATEST_URL)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["run_id"], str(latest))
        self.assertNotIn("requested_by", body)
        self.assertEqual(body["quality"]["optional_steps"]["eval_snapshot"], "failed")
        self.assertEqual((body["status"], body["phase"], body["week_from"]), ("completed", "done", closed_week().isoformat()))

    def test_no_runs_is_404(self):
        client, _ = _client()
        response = client.get(LATEST_URL)
        self.assertEqual((response.status_code, response.json()["code"]), (404, "pipeline_run_not_found"))

    def test_missing_reporting_schema_is_503(self):
        client, _ = _client(tables=False)
        for url in (LATEST_URL, WEEKLY_URL):
            with self.subTest(url=url):
                response = client.get(url)
                self.assertEqual((response.status_code, response.json()["code"]), (503, "storage_unavailable"))

    def test_without_token_is_401(self):
        client, _ = _client()
        client.headers.pop("Authorization")
        self.assertEqual(client.get(LATEST_URL).status_code, 401)


@mock.patch("reporting.router.request_manual_run")
class ManualRunTests(unittest.TestCase):
    def test_admin_gets_202_with_the_flow_run_id(self, trigger):
        flow_run_id = uuid4()
        trigger.return_value = TriggeredRun(prefect_flow_run_id=flow_run_id)
        client, admin = _client(UserRole.ADMIN)
        response = client.post(RUNS_URL, json={"week_start": closed_week().isoformat()})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json(), {"prefect_flow_run_id": str(flow_run_id), "status": "scheduled"})
        trigger.assert_called_once_with(FAKE_PREFECT_URL, week_start=closed_week(), requested_by=admin.id)

    def test_without_body_the_flow_picks_the_last_closed_week(self, trigger):
        trigger.return_value = TriggeredRun(prefect_flow_run_id=uuid4())
        client, admin = _client(UserRole.ADMIN)
        self.assertEqual(client.post(RUNS_URL).status_code, 202)
        trigger.assert_called_once_with(FAKE_PREFECT_URL, week_start=None, requested_by=admin.id)

    def test_requested_by_never_comes_from_the_body(self, trigger):
        client, _ = _client(UserRole.ADMIN)
        response = client.post(RUNS_URL, json={"requested_by": str(uuid4())})
        self.assertEqual(response.status_code, 422)
        trigger.assert_not_called()

    def test_non_admin_is_403_and_no_token_is_401(self, trigger):
        client, _ = _client(UserRole.USER)
        self.assertEqual(client.post(RUNS_URL).status_code, 403)
        client.headers.pop("Authorization")
        self.assertEqual(client.post(RUNS_URL).status_code, 401)
        trigger.assert_not_called()

    def test_invalid_weeks_are_422(self, trigger):
        client, _ = _client(UserRole.ADMIN)
        for week in (closed_week() + timedelta(days=2), closed_week() + timedelta(weeks=1), closed_week(13)):
            with self.subTest(week=week):
                response = client.post(RUNS_URL, json={"week_start": week.isoformat()})
                self.assertEqual((response.status_code, response.json()["code"]), (422, "validation_error"))
        trigger.assert_not_called()

    def test_running_row_in_the_log_is_409(self, trigger):
        client, _ = _client(UserRole.ADMIN)
        add_run(client, week_from=closed_week(), status="running")
        response = client.post(RUNS_URL)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "pipeline_run_in_progress"))
        trigger.assert_not_called()

    def test_stale_running_row_does_not_block(self, trigger):
        trigger.return_value = TriggeredRun(prefect_flow_run_id=uuid4())
        client, _ = _client(UserRole.ADMIN)
        add_run(client, week_from=closed_week(), status="running", started_at=datetime.now(UTC) - timedelta(minutes=31))
        self.assertEqual(client.post(RUNS_URL).status_code, 202)

    def test_active_flow_run_in_prefect_is_409(self, trigger):
        trigger.side_effect = RunAlreadyActiveError()
        client, _ = _client(UserRole.ADMIN)
        response = client.post(RUNS_URL)
        self.assertEqual((response.status_code, response.json()["code"]), (409, "pipeline_run_in_progress"))

    def test_prefect_down_is_503(self, trigger):
        trigger.side_effect = PipelineUnavailableError("URLError")
        client, _ = _client(UserRole.ADMIN)
        response = client.post(RUNS_URL)
        self.assertEqual((response.status_code, response.json()["code"]), (503, "pipeline_unavailable"))
        self.assertNotIn("prefect.invalid", response.text)

    def test_prefect_not_configured_is_503(self, trigger):
        client, _ = _client(UserRole.ADMIN, prefect_url="")
        response = client.post(RUNS_URL)
        self.assertEqual((response.status_code, response.json()["code"]), (503, "pipeline_unavailable"))
        trigger.assert_not_called()


class SettingsTests(unittest.TestCase):
    def test_prefect_url_comes_from_the_environment_and_is_optional(self):
        self.assertEqual(Settings.from_env({"PIPELINE_PREFECT_API_URL": " http://prefect-server:4200/api "})
                         .pipeline_prefect_api_url, "http://prefect-server:4200/api")
        self.assertEqual(Settings.from_env({}).pipeline_prefect_api_url, "")

    def test_prefect_url_must_be_http(self):
        from app.core.config import ConfigError  # noqa: PLC0415

        with self.assertRaises(ConfigError):
            Settings(pipeline_prefect_api_url="ftp://prefect")


if __name__ == "__main__":
    unittest.main()
