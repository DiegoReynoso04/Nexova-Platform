import sys
import tempfile
import unittest
from pathlib import Path

from job_runner.config import ConfigError, resolve_database_target, target_from_url

URL = "postgresql://nexova_app:s3cretPass@127.0.0.1:55432/nexova_test"
REPO_ROOT = Path(__file__).resolve().parents[3]


class ConfigTests(unittest.TestCase):
    def env_file(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / ".env"
        path.write_text(content, encoding="utf-8")
        return path

    def test_environment_wins_over_the_env_file(self):
        target = resolve_database_target({"DATABASE_URL": URL}, self.env_file("DATABASE_URL=postgresql://u:p@other:1/db\n"))
        self.assertEqual((target.source, target.host, target.is_local), ("entorno", "127.0.0.1", True))
        self.assertTrue(target.url.startswith("postgresql+psycopg2://"))

    def test_env_file_only_reads_that_key(self):
        path = self.env_file("# c\nJWT_SECRET_KEY=zzzz\nexport DATABASE_URL='postgresql://u:p@db.example:6543/x'\n")
        target = resolve_database_target({}, path)
        self.assertEqual((target.source, target.host, target.is_local), (".env de la raíz", "db.example", False))

    def test_missing_or_invalid_configuration(self):
        with self.assertRaises(ConfigError):
            resolve_database_target({}, Path("does-not-exist.env"))
        for bad in ("mysql://u:p@h/db", "postgresql://u:p@/db"):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                target_from_url(bad, "entorno")

    def test_repr_and_describe_never_show_the_url(self):
        target = target_from_url(URL, "entorno")
        for text in (repr(target), target.describe(), str(ConfigError("x"))):
            self.assertNotIn("s3cretPass", text)
            self.assertNotIn("nexova_app", text)

    def test_same_resolution_as_the_pipeline_that_the_script_launches(self):
        """El export y el hijo (pipeline.py) deben apuntar siempre a la misma base."""
        sys.path.insert(0, str(REPO_ROOT / "data" / "pipelines"))
        self.addCleanup(sys.path.remove, str(REPO_ROOT / "data" / "pipelines"))
        from business_performance import config as pipeline_config

        env_file = self.env_file("DATABASE_URL=postgresql://u:p@db.example:6543/x\n")
        for environ in ({"DATABASE_URL": URL}, {}, {"DATABASE_URL": "  "}):
            with self.subTest(environ=environ):
                mine = resolve_database_target(environ, env_file)
                theirs = pipeline_config.resolve_database_target(environ, env_file)
                self.assertEqual((mine.url, mine.source, mine.host), (theirs.url, theirs.source, theirs.host))
