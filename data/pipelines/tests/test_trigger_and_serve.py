"""`trigger.py` contra la REST real de Prefect (`prefect_test_harness`) y los deployments de `serve.py`."""

import ast
import sys
import unittest
from pathlib import Path
from uuid import uuid4

from business_performance import serve, trigger
from business_performance.trigger import PipelineUnavailableError, RunAlreadyActiveError, request_manual_run
from nexova_shared.reporting import PIPELINE_NAME
from prefect.client.orchestration import get_client
from prefect.settings import PREFECT_API_URL
from prefect.testing.utilities import prefect_test_harness

from tests.support import closed_week

TRIGGER_SOURCE = Path(trigger.__file__)

_harness = None


def setUpModule():
    global _harness
    _harness = prefect_test_harness(server_startup_timeout=60)
    _harness.__enter__()


def tearDownModule():
    _harness.__exit__(None, None, None)


class TriggerAgainstPrefectTests(unittest.TestCase):
    def setUp(self):
        self.api_url = PREFECT_API_URL.value()
        with get_client(sync_client=True) as client:
            flow_id = client.create_flow_from_name(trigger.FLOW_NAME)
            self.deployment_id = client.create_deployment(flow_id=flow_id, name=trigger.MANUAL_DEPLOYMENT)
        self.addCleanup(self._delete_deployment)

    def _delete_deployment(self):
        with get_client(sync_client=True) as client:
            client.delete_deployment(self.deployment_id)

    def test_creates_a_scheduled_flow_run_with_the_flow_parameters(self):
        user = uuid4()
        run = request_manual_run(self.api_url, week_start=closed_week(), requested_by=user)
        self.assertEqual(run.status, "scheduled")
        with get_client(sync_client=True) as client:
            flow_run = client.read_flow_run(run.prefect_flow_run_id)
        self.assertEqual(flow_run.deployment_id, self.deployment_id)
        self.assertEqual(flow_run.state.type.value, "SCHEDULED")
        self.assertEqual(flow_run.parameters, {
            "trigger": "manual", "week_start": closed_week().isoformat(), "requested_by": str(user)})

    def test_a_second_request_while_one_is_active_is_refused(self):
        request_manual_run(self.api_url)
        with self.assertRaises(RunAlreadyActiveError):
            request_manual_run(self.api_url)

    def test_missing_deployment_is_unavailable(self):
        self._delete_deployment()
        self.addCleanup(lambda: None)
        with get_client(sync_client=True) as client:
            flow_id = client.create_flow_from_name(trigger.FLOW_NAME)
            self.deployment_id = client.create_deployment(flow_id=flow_id, name="other")
        with self.assertRaises(PipelineUnavailableError):
            request_manual_run(self.api_url)


class TriggerOfflineTests(unittest.TestCase):
    def test_unreachable_server_is_unavailable_without_the_url(self):
        url = "http://127.0.0.1:9/api"
        with self.assertRaises(PipelineUnavailableError) as raised:
            request_manual_run(url, timeout=2)
        self.assertNotIn("127.0.0.1", str(raised.exception))

    def test_invalid_url_is_unavailable(self):
        with self.assertRaises(PipelineUnavailableError):
            request_manual_run("file:///etc/passwd")

    def test_names_match_the_flow_and_the_shared_vocabulary(self):
        self.assertEqual(trigger.FLOW_NAME, PIPELINE_NAME)

    def test_only_standard_library_imports(self):
        tree = ast.parse(TRIGGER_SOURCE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "trigger.py must not import from its own package")
                names = [node.module or ""]
            else:
                continue
            for name in names:
                with self.subTest(module=name):
                    self.assertIn(name.split(".")[0], sys.stdlib_module_names | {"__future__"})


class ServeTests(unittest.TestCase):
    def test_manual_and_weekly_deployments(self):
        manual, weekly = serve.build_deployments()
        self.assertEqual((manual.name, weekly.name), ("manual", "weekly"))
        self.assertEqual(manual.parameters, {"trigger": "manual"})
        self.assertEqual(weekly.parameters, {"trigger": "schedule"})
        self.assertEqual(manual.schedules or [], [])
        (schedule,) = weekly.schedules
        self.assertEqual((schedule.schedule.cron, schedule.schedule.timezone), ("0 6 * * 1", "Europe/Madrid"))
        for deployment in (manual, weekly):
            with self.subTest(deployment=deployment.name):
                limit = deployment.concurrency_limit
                self.assertEqual(getattr(limit, "limit", limit), 1)


if __name__ == "__main__":
    unittest.main()
