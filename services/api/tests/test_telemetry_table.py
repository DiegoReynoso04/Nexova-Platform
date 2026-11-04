"""Tabla `telemetry_events` y su migración (ticket de almacenamiento, D1–D4).

Ningún test conecta con Supabase: el DDL se compila con el dialecto de
PostgreSQL y lo demás, en SQLite. El efecto real del `REVOKE` solo se ve en un
PostgreSQL con un rol sin superusuario (docs/telemetry/storage-analysis.md §5.3).
"""

import unittest
from unittest import mock
from uuid import uuid4

from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import Session

from app.core.config import Settings
from app.modules.inventory.database import build_engine, init_db
from app.modules.inventory.models import INVENTORY_TABLES, utc_now
from app.modules.telemetry import migrate
from app.modules.telemetry.models import SERVICE_CHECK, TAGS_INDEX, TELEMETRY_EVENTS_TABLE, TelemetryEventRecord

from .support import TEST_DATABASE_URL, capture_logs

TABLE = TelemetryEventRecord.__table__  # type: ignore[attr-defined]
COLUMNS = ["event_id", "event_type", "timestamp", "service", "user_id", "session_id", "schema_version", "tags"]
EMPTY = migrate.DatabaseState(False, frozenset(), False, frozenset(), ())
ALL_INDEXES = frozenset({"ix_telemetry_events_timestamp", "ix_telemetry_events_event_type", TAGS_INDEX})
HOST = "db.example.invalid"
POSTGRES_URL = f"postgresql://probeuser:probe-secret-value@{HOST}:6543/postgres"


def postgres_ddl() -> str:
    dialect = postgresql.dialect()
    return "\n".join(
        [str(CreateTable(TABLE).compile(dialect=dialect))] + [str(CreateIndex(index).compile(dialect=dialect)) for index in TABLE.indexes]
    )


def record(**changes: object) -> TelemetryEventRecord:
    values: dict[str, object] = {
        "event_id": uuid4(),
        "event_type": "page_viewed",
        "timestamp": utc_now(),
        "service": "backoffice",
        "schema_version": "1.0.0",
        "tags": {},
    }
    return TelemetryEventRecord(**(values | changes))


class SchemaTests(unittest.TestCase):
    def test_exactly_the_eight_columns_in_order(self) -> None:
        self.assertEqual([column.name for column in TABLE.columns], COLUMNS)

    def test_postgresql_types_and_nullability(self) -> None:
        ddl = " ".join(postgres_ddl().split())
        for fragment in (
            "event_id UUID NOT NULL",
            "event_type VARCHAR(64) NOT NULL",
            "timestamp TIMESTAMP WITH TIME ZONE NOT NULL",
            "service VARCHAR(16) NOT NULL",
            "user_id UUID,",
            "session_id UUID,",
            "schema_version VARCHAR(16) NOT NULL",
            "tags JSONB NOT NULL",
            "PRIMARY KEY (event_id)",
        ):
            with self.subTest(fragment):
                self.assertIn(fragment, ddl)

    def test_service_is_a_closed_vocabulary(self) -> None:
        self.assertIn(f"CONSTRAINT {SERVICE_CHECK} CHECK (service IN ('backoffice', 'api'))", " ".join(postgres_ddl().split()))

    def test_three_indexes_and_tags_uses_gin(self) -> None:
        ddl = postgres_ddl()
        self.assertEqual({index.name for index in TABLE.indexes}, set(ALL_INDEXES))
        self.assertIn(f"CREATE INDEX {TAGS_INDEX} ON {TELEMETRY_EVENTS_TABLE} USING gin (tags)", ddl)
        self.assertIn(f"CREATE INDEX ix_telemetry_events_timestamp ON {TELEMETRY_EVENTS_TABLE} (timestamp)", ddl)
        self.assertIn(f"CREATE INDEX ix_telemetry_events_event_type ON {TELEMETRY_EVENTS_TABLE} (event_type)", ddl)

    def test_the_check_and_the_primary_key_apply_in_a_real_database(self) -> None:
        engine = build_engine(TEST_DATABASE_URL)
        self.addCleanup(engine.dispose)
        TABLE.create(engine)
        with Session(engine) as session, self.assertRaises(IntegrityError):
            session.add(record(service="frontend"))
            session.commit()
        repeated = uuid4()
        with Session(engine) as session:
            session.add(record(event_id=repeated))
            session.commit()
        with Session(engine) as session, self.assertRaises(IntegrityError):
            session.add(record(event_id=repeated))
            session.commit()


class TableIsNotCreatedAtStartupTests(unittest.TestCase):
    """D3: arrancar la API contra la demo no puede crear la tabla sin confirmación."""

    def test_it_is_not_an_inventory_table(self) -> None:
        self.assertNotIn(TELEMETRY_EVENTS_TABLE, {table.name for table in INVENTORY_TABLES})

    def test_init_db_does_not_create_it(self) -> None:
        engine = build_engine(TEST_DATABASE_URL)
        self.addCleanup(engine.dispose)
        init_db(engine)
        self.assertNotIn(TELEMETRY_EVENTS_TABLE, inspect(engine).get_table_names())


class PendingStatementsTests(unittest.TestCase):
    def test_a_new_database_needs_everything_in_order(self) -> None:
        statements = migrate.pending_statements(EMPTY)
        self.assertEqual(len(statements), 6)
        self.assertTrue(statements[0].startswith(f"CREATE TABLE IF NOT EXISTS {TELEMETRY_EVENTS_TABLE}"))
        self.assertTrue(all(statement.startswith("CREATE INDEX IF NOT EXISTS") for statement in statements[1:4]))
        self.assertEqual(statements[4], f"ALTER TABLE {TELEMETRY_EVENTS_TABLE} ENABLE ROW LEVEL SECURITY")
        self.assertEqual(statements[5], f"REVOKE UPDATE, DELETE, TRUNCATE ON {TELEMETRY_EVENTS_TABLE} FROM PUBLIC, CURRENT_USER")

    def test_the_revoke_reaches_the_supabase_roles_that_exist(self) -> None:
        statements = migrate.pending_statements(migrate.DatabaseState(False, frozenset(), False, frozenset(), ("anon", "service_role")))
        self.assertTrue(statements[-1].endswith("FROM PUBLIC, CURRENT_USER, anon, service_role"))

    def test_nothing_pending_when_everything_is_in_place(self) -> None:
        self.assertEqual(migrate.pending_statements(migrate.DatabaseState(True, ALL_INDEXES, True, frozenset(), ())), [])

    def test_only_the_missing_pieces(self) -> None:
        missing_gin = migrate.DatabaseState(True, ALL_INDEXES - {TAGS_INDEX}, True, frozenset(), ())
        self.assertEqual(len(migrate.pending_statements(missing_gin)), 1)
        writable = migrate.DatabaseState(True, ALL_INDEXES, True, frozenset({"postgres"}), ())
        self.assertEqual(migrate.pending_statements(writable), [migrate.revoke_statement(())])
        no_rls = migrate.DatabaseState(True, ALL_INDEXES, False, frozenset(), ())
        self.assertEqual(len(migrate.pending_statements(no_rls)), 1)

    def test_no_statement_writes_or_deletes_rows(self) -> None:
        for statement in migrate.pending_statements(EMPTY):
            for verb in ("INSERT", "DROP", "DELETE FROM", "UPDATE "):
                self.assertFalse(statement.startswith(verb), statement)


class MigrationCommandTests(unittest.TestCase):
    def stderr_of(self, *args: object, **kwargs: object) -> tuple[int, str]:
        with capture_logs(), mock.patch("sys.stderr") as stderr:
            code = migrate.run(*args, **kwargs)  # type: ignore[arg-type]
        return code, "".join(call.args[0] for call in stderr.write.call_args_list)

    def test_only_postgresql(self) -> None:
        code, written = self.stderr_of(["--dry-run"], settings=Settings(database_url="sqlite://"))
        self.assertEqual(code, migrate.CONFIG_ERROR_EXIT)
        self.assertIn("solo se aplica a PostgreSQL", written)

    def test_without_database_url(self) -> None:
        self.assertEqual(self.stderr_of([], settings=Settings())[0], migrate.CONFIG_ERROR_EXIT)

    def test_a_superuser_is_refused(self) -> None:
        with mock.patch.object(migrate, "migrate", side_effect=migrate.SuperuserError()):
            code, written = self.stderr_of(["--dry-run"], settings=Settings(database_url=POSTGRES_URL))
        self.assertEqual(code, migrate.CONFIG_ERROR_EXIT)
        self.assertIn("superusuario", written)

    def test_a_role_that_keeps_write_privileges_is_refused(self) -> None:
        with mock.patch.object(migrate, "migrate", side_effect=migrate.StillWritableError()):
            code, written = self.stderr_of([], settings=Settings(database_url=POSTGRES_URL))
        self.assertEqual(code, migrate.CONFIG_ERROR_EXIT)
        self.assertIn("deshecho", written)

    def test_an_unavailable_database_names_only_the_class(self) -> None:
        failure = OperationalError("SELECT", {}, Exception(f"could not connect to {HOST}"))
        with mock.patch.object(migrate, "migrate", side_effect=failure):
            code, written = self.stderr_of([], settings=Settings(database_url=POSTGRES_URL))
        self.assertEqual(code, migrate.DATABASE_UNAVAILABLE_EXIT)
        self.assertIn("OperationalError", written)
        self.assertNotIn(HOST, written)
        self.assertNotIn("probe-secret-value", written)


if __name__ == "__main__":
    unittest.main()
