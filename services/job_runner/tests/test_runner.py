import unittest

from job_runner import JobRunRepository

from .cases import RunnerCases
from .support import TABLE, FakeClock, sqlite_engine


class SqliteRunnerTests(RunnerCases, unittest.TestCase):
    def setUp(self):
        self.engine = sqlite_engine()
        self.addCleanup(self.engine.dispose)
        self.table = TABLE
        self.repo = JobRunRepository(self.engine, self.table)
        self.clock = FakeClock()
        self.setUp_logging()
