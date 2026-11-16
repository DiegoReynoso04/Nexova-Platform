"""El subproceso del pipeline con hijos falsos (procesos reales, sin Prefect ni base)."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from .support import load_script

script = load_script()
WEEK = date(2026, 10, 26)
URL = "postgresql+psycopg2://nexova_app:s3cretPass@127.0.0.1:5432/nexova_test"


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # Un zombi sin recoger sigue «vivo» para kill(0): se mira su estado.
    try:
        return Path(f"/proc/{pid}/stat").read_text().split(") ")[-1].split()[0] != "Z"
    except OSError:
        return False


class ChildTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)

    def fake_pipeline(self, body: str) -> Path:
        path = self.dir / "pipeline.py"
        path.write_text(textwrap.dedent(body), encoding="utf-8")
        return path

    def run_fake(self, body: str, **kwargs):
        with mock.patch.object(script, "PIPELINE_SCRIPT", self.fake_pipeline(body)):
            return script.run_pipeline(WEEK, URL, **kwargs)

    def test_exit_0_is_success(self):
        self.assertIsNone(self.run_fake("import sys; sys.exit(0)"))

    def test_exit_codes_map_to_fixed_messages(self):
        cases = {1: "exited with code 1 (run failed", 2: "exited with code 2 (configuration", 7: "exited with code 7"}
        for code, expected in cases.items():
            with self.subTest(code=code), self.assertRaisesRegex(script.PipelineError, expected.replace("(", r"\(")):
                self.run_fake(f"import sys; sys.exit({code})")

    def test_the_child_output_never_enters_the_error_message(self):
        body = "import sys; print('postgresql://u:topSecretPw@db.example/x', file=sys.stderr); sys.exit(1)"
        with self.assertRaises(script.PipelineError) as caught:
            self.run_fake(body)
        self.assertNotIn("topSecretPw", str(caught.exception))
        self.assertNotIn("db.example", str(caught.exception))

    def test_same_interpreter_week_start_cwd_and_a_whitelisted_environment(self):
        out = self.dir / "seen.json"
        body = f"""
            import json, os, sys
            json.dump({{"exe": sys.executable, "argv": sys.argv[1:], "cwd": os.getcwd(), "env": dict(os.environ)}},
                      open({str(out)!r}, "w"))
        """
        leaked = {"JWT_SECRET_KEY": "j" * 40, "TELEMETRY_SUPPLIER_KEY": "t" * 40, "RESEND_API_KEY": "r" * 40,
                  "SOME_OTHER": "x", "DATABASE_URL": "postgresql://wrong:wrong@elsewhere/db", "PREFECT_API_URL": "http://p:4200/api",
                  "DO_NOT_TRACK": "1"}
        with mock.patch.dict(os.environ, leaked):
            self.run_fake(body)
        seen = json.loads(out.read_text())
        self.assertEqual(seen["exe"], sys.executable)
        self.assertEqual(seen["argv"], ["--week-start", "2026-10-26"])
        self.assertEqual(Path(seen["cwd"]).resolve(), script.REPO_ROOT.resolve())
        env = seen["env"]
        for name in ("JWT_SECRET_KEY", "TELEMETRY_SUPPLIER_KEY", "RESEND_API_KEY", "SOME_OTHER"):
            self.assertNotIn(name, env)
        self.assertEqual(env["DATABASE_URL"], URL)  # la del script, no la del entorno heredado
        self.assertEqual(env["PREFECT_API_URL"], "http://p:4200/api")
        self.assertEqual(env["DO_NOT_TRACK"], "1")

    def test_child_environment_is_a_whitelist(self):
        env = script.child_environment(URL, {"PATH": "/bin", "JWT_SECRET_KEY": "x" * 40, "PREFECT_HOME": "/p", "FOO": "1"})
        self.assertEqual(env, {"PATH": "/bin", "PREFECT_HOME": "/p", "DATABASE_URL": URL})

    def test_timeout_kills_the_child_and_its_grandchild(self):
        pid_file = self.dir / "grandchild.pid"
        body = f"""
            import subprocess, sys, time
            grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
            open({str(pid_file)!r}, "w").write(str(grandchild.pid))
            time.sleep(120)
        """
        started = time.monotonic()
        with self.assertRaisesRegex(script.PipelineError, "timed out after 2 s and was killed"):
            self.run_fake(body, timeout=2)
        self.assertLess(time.monotonic() - started, 40)
        grandchild = int(pid_file.read_text())
        for _ in range(50):
            if not pid_alive(grandchild):
                break
            time.sleep(0.2)
        self.assertFalse(pid_alive(grandchild), "the grandchild survived the timeout")

    def test_the_default_timeout_is_20_minutes(self):
        self.assertEqual(script.PIPELINE_TIMEOUT_SECONDS, 1200)

    def test_an_exception_while_waiting_kills_the_child(self):
        pid_file = self.dir / "child.pid"
        body = f"import os, time; open({str(pid_file)!r}, 'w').write(str(os.getpid())); time.sleep(120)"

        class Interrupted(Exception):
            pass

        real_wait = subprocess.Popen.wait

        def wait(self, timeout=None):
            for _ in range(100):  # espera a que el hijo escriba su pid
                if pid_file.exists() and pid_file.read_text():
                    break
                time.sleep(0.1)
            raise Interrupted()

        with mock.patch.object(subprocess.Popen, "wait", wait), self.assertRaises(Interrupted):
            self.run_fake(body)
        child = int(pid_file.read_text())
        for _ in range(50):
            if not pid_alive(child):
                break
            time.sleep(0.2)
        self.assertFalse(pid_alive(child))
        self.assertTrue(callable(real_wait))
