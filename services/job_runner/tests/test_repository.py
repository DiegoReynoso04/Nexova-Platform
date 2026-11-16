import unittest

from job_runner import JobRunRepository

from .cases import RepositoryCases
from .support import TABLE, sqlite_engine


class SqliteRepositoryTests(RepositoryCases, unittest.TestCase):
    def setUp(self):
        self.engine = sqlite_engine()
        self.addCleanup(self.engine.dispose)
        self.table = TABLE
        self.repo = JobRunRepository(self.engine, self.table)

    def test_invalid_table_names_are_refused(self):
        for name in ("job_runs; DROP TABLE x", "Job Runs", "a.b.c", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                JobRunRepository(self.engine, name)

    def test_schema_not_ready_without_the_table(self):
        self.assertFalse(JobRunRepository(self.engine, "missing_table").schema_ready())
