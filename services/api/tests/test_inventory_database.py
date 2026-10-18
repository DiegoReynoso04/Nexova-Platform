"""Hito 5, F2: configuración, motor, modelos ORM, `get_db`, RLS y 503 del inventario.

Ningún test conecta con Supabase: SQLite en memoria (`sqlite://`) para lo que
necesita una base real y el dialecto de PostgreSQL, sin conexión, para el DDL,
el driver y las sentencias de RLS. Datos ficticios (`example.invalid`).
"""

import ast
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Enum, create_mock_engine, event, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.pool import NullPool, StaticPool
from sqlalchemy.schema import CreateIndex, CreateTable
from sqlmodel import Session, SQLModel

from app.core.config import ConfigError, Settings
from app.main import create_app
from app.modules.inventory import database
from app.modules.inventory.database import (
    CONNECT_TIMEOUT_SECONDS,
    build_engine,
    enable_row_level_security,
    get_db,
    init_db,
)
from app.modules.inventory.models import INVENTORY_TABLES, Asset, AssetEntry, AssetExit

from .support import APP_DIR, TEST_DATABASE_URL, capture_logs, with_test_auth

INVENTORY_TABLE_NAMES = {"assets", "asset_entries", "asset_exits"}
# Credenciales y host ficticios: ningún mensaje de error ni log debe repetirlos.
SECRET = "probe-secret-value"
USER = "probeuser"
HOST = "db.example.invalid"
POSTGRES_URL = f"postgresql://{USER}:{SECRET}@{HOST}:6543/postgres"
JWT_ENV = {"JWT_SECRET_KEY": "k" * 40, "ACCESS_TOKEN_EXPIRE_MINUTES": "30"}


def inventory_settings(tmp: str) -> Settings:
    return with_test_auth(Settings(), Path(tmp) / "auth.json")


def assert_no_secrets(case: unittest.TestCase, text_value: str) -> None:
    for secret in (SECRET, USER, HOST):
        case.assertNotIn(secret, text_value)


def postgres_ddl() -> str:
    dialect = postgresql.dialect()
    statements = [str(CreateTable(table).compile(dialect=dialect)) for table in INVENTORY_TABLES]
    statements += [str(CreateIndex(index).compile(dialect=dialect)) for table in INVENTORY_TABLES for index in table.indexes]
    return "\n".join(statements)


def sqlite_engine():  # type: ignore[no-untyped-def]
    engine = build_engine(TEST_DATABASE_URL)
    init_db(engine)
    return engine


def asset(**changes: Any) -> Asset:
    values = {"name": "Example asset", "sku": "EXAMPLE-SKU-1", "category": "hardware", "office": "Valencia"}
    return Asset(**(values | changes))


def entry(asset_id: int, **changes: Any) -> AssetEntry:
    values = {
        "asset_id": asset_id,
        "quantity": 3,
        "supplier": "Example supplier",
        "office": "Valencia",
        "user_uuid": "00000000-0000-4000-8000-000000000000",
    }
    return AssetEntry(**(values | changes))


def exit_order(asset_id: int, **changes: Any) -> AssetExit:
    values = {
        "asset_id": asset_id,
        "quantity": 1,
        "exit_type": "consumption",
        "assigned_to": None,
        "office": "Valencia",
        "user_uuid": "00000000-0000-4000-8000-000000000000",
    }
    return AssetExit(**(values | changes))


class DatabaseUrlConfigTests(unittest.TestCase):
    def test_environment_accepts_only_postgresql_schemes(self) -> None:
        for scheme in ("postgresql", "postgresql+psycopg2"):
            with self.subTest(scheme=scheme):
                url = f"{scheme}://{USER}:{SECRET}@{HOST}:6543/postgres"
                settings = Settings.from_env({**JWT_ENV, "DATABASE_URL": f"  {url}  "})
                self.assertEqual(settings.database_url, url)
                settings.require_database()

    def test_environment_rejects_other_schemes_without_repeating_the_url(self) -> None:
        for url in (
            "sqlite://",
            "sqlite:///inventory.db",
            f"postgres://{USER}:{SECRET}@{HOST}/postgres",
            f"postgresql+psycopg://{USER}:{SECRET}@{HOST}/postgres",
            f"mysql://{USER}:{SECRET}@{HOST}/inventory",
            f"{USER}:{SECRET}@{HOST}",
        ):
            with self.subTest(url=url), self.assertRaises(ConfigError) as error:
                Settings.from_env({**JWT_ENV, "DATABASE_URL": url})
            self.assertIn("DATABASE_URL", str(error.exception))
            assert_no_secrets(self, str(error.exception))

    def test_app_does_not_start_without_database_url(self) -> None:
        settings = Settings.from_env(JWT_ENV)
        self.assertEqual(settings.database_url, "")
        with self.assertRaises(ConfigError) as error:
            create_app(settings)
        self.assertIn("DATABASE_URL", str(error.exception))

    def test_jwt_settings_are_still_checked_first(self) -> None:
        with self.assertRaises(ConfigError) as error:
            create_app(Settings.from_env({"DATABASE_URL": POSTGRES_URL}))
        self.assertIn("JWT_SECRET_KEY", str(error.exception))

    def test_database_url_never_appears_in_repr(self) -> None:
        settings = Settings.from_env({**JWT_ENV, "DATABASE_URL": POSTGRES_URL})
        assert_no_secrets(self, repr(settings))

    def test_tests_can_inject_sqlite_directly(self) -> None:
        # Sin validación en __post_init__: solo `from_env` restringe el esquema.
        settings = Settings(database_url=TEST_DATABASE_URL)
        settings.require_database()
        self.assertEqual(settings.database_url, TEST_DATABASE_URL)


class EngineTests(unittest.TestCase):
    def test_postgresql_url_uses_psycopg2_without_connecting(self) -> None:
        # SQLAlchemy 2.1 resuelve `postgresql://` con psycopg (v3), que no está instalado.
        for url in (POSTGRES_URL, POSTGRES_URL.replace("postgresql://", "postgresql+psycopg2://")):
            with self.subTest(url=url.partition(":")[0]):
                engine = build_engine(url)
                self.assertEqual(engine.dialect.name, "postgresql")
                self.assertEqual(engine.dialect.driver, "psycopg2")
                self.assertEqual(engine.url.drivername, "postgresql+psycopg2")
                self.assertIsInstance(engine.pool, NullPool)
                self.assertTrue(engine.hide_parameters)

    def test_postgresql_connections_have_a_timeout(self) -> None:
        engine = build_engine(POSTGRES_URL)
        captured: dict[str, Any] = {}

        class Stop(Exception):
            pass

        @event.listens_for(engine, "do_connect")
        def capture(dialect: Any, record: Any, cargs: Any, cparams: dict[str, Any]) -> None:
            captured.update(cparams)
            raise Stop  # nunca llega a abrir el socket

        with self.assertRaises(Stop):
            engine.connect()
        self.assertEqual(captured["connect_timeout"], CONNECT_TIMEOUT_SECONDS)

    def test_invalid_url_raises_config_error_without_the_url(self) -> None:
        for url in (f"postgresql://{USER}:{SECRET}@{HOST}:notaport/postgres", "not a url"):
            with self.subTest(url=url), self.assertRaises(ConfigError) as error:
                build_engine(url)
            assert_no_secrets(self, str(error.exception))
            self.assertIsNone(error.exception.__cause__)
            self.assertIsNone(error.exception.__context__)

    def test_sqlite_engine_shares_one_connection_with_foreign_keys_on(self) -> None:
        engine = build_engine(TEST_DATABASE_URL)
        self.assertIsInstance(engine.pool, StaticPool)
        self.assertTrue(engine.hide_parameters)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text("PRAGMA foreign_keys")).scalar_one(), 1)


class SchemaTests(unittest.TestCase):
    def test_only_the_three_inventory_tables_and_no_users_table(self) -> None:
        self.assertEqual(set(SQLModel.metadata.tables), INVENTORY_TABLE_NAMES)
        self.assertEqual({table.name for table in INVENTORY_TABLES}, INVENTORY_TABLE_NAMES)
        for table in INVENTORY_TABLES:
            self.assertNotIn("user_id", table.columns)

    def test_postgresql_ddl_has_real_foreign_keys_unique_sku_and_timestamptz(self) -> None:
        ddl = postgres_ddl()
        self.assertEqual(ddl.count("FOREIGN KEY(asset_id) REFERENCES assets (id)"), 2)
        self.assertIn("UNIQUE (sku)", ddl)
        self.assertEqual(ddl.count("created_at TIMESTAMP WITH TIME ZONE NOT NULL"), 2)
        self.assertIn("CREATE INDEX ix_asset_entries_asset_id ON asset_entries (asset_id)", ddl)
        self.assertIn("CREATE INDEX ix_asset_exits_asset_id ON asset_exits (asset_id)", ddl)
        # user_uuid es una cadena sin FK: no hay tabla de usuarios en Supabase.
        self.assertEqual(ddl.count("user_uuid VARCHAR(36) NOT NULL"), 2)
        self.assertEqual(ddl.count("REFERENCES"), 2)

    def test_no_native_enum_types(self) -> None:
        self.assertNotIn("ENUM", postgres_ddl().upper())
        for table in INVENTORY_TABLES:
            for column in table.columns:
                with self.subTest(column=f"{table.name}.{column.name}"):
                    self.assertNotIsInstance(column.type, Enum)

    def test_postgresql_ddl_has_the_check_constraints(self) -> None:
        ddl = postgres_ddl()
        for fragment in (
            "CONSTRAINT ck_assets_category CHECK (category IN ('hardware', 'peripherals', 'office_supplies', 'training_materials'))",
            "CONSTRAINT ck_assets_office CHECK (office IN ('Valencia', 'Miami'))",
            "CONSTRAINT ck_asset_entries_quantity_positive CHECK (quantity > 0)",
            "CONSTRAINT ck_asset_entries_office CHECK (office IN ('Valencia', 'Miami'))",
            "CONSTRAINT ck_asset_exits_quantity_positive CHECK (quantity > 0)",
            "CONSTRAINT ck_asset_exits_office CHECK (office IN ('Valencia', 'Miami'))",
            "CONSTRAINT ck_asset_exits_exit_type CHECK (exit_type IN ('allocation', 'consumption'))",
            "CONSTRAINT ck_asset_exits_assigned_to CHECK (exit_type = 'allocation' AND assigned_to IS NOT NULL "
            "OR exit_type = 'consumption' AND assigned_to IS NULL)",
        ):
            with self.subTest(fragment=fragment.split(" CHECK")[0]):
                self.assertIn(fragment, ddl)

    def test_current_stock_is_not_a_column(self) -> None:
        for table in INVENTORY_TABLES:
            self.assertNotIn("current_stock", table.columns)


class SqliteConstraintTests(unittest.TestCase):
    """Las restricciones se aplican de verdad en la base (SQLite con `foreign_keys=ON`)."""

    def setUp(self) -> None:
        self.engine = sqlite_engine()
        self.addCleanup(self.engine.dispose)
        with Session(self.engine) as session:
            stored = asset()
            session.add(stored)
            session.commit()
            assert stored.id is not None
            self.asset_id = stored.id

    def assertRejected(self, row: Any) -> None:
        with Session(self.engine) as session:
            session.add(row)
            with self.assertRaises(IntegrityError):
                session.commit()

    def test_init_db_creates_the_three_tables_and_is_idempotent(self) -> None:
        init_db(self.engine)
        self.assertTrue(INVENTORY_TABLE_NAMES <= set(inspect(self.engine).get_table_names()))

    def test_foreign_key_is_enforced(self) -> None:
        self.assertRejected(entry(self.asset_id + 999))
        self.assertRejected(exit_order(self.asset_id + 999))

    def test_valid_rows_are_stored_with_created_at(self) -> None:
        with Session(self.engine) as session:
            session.add(entry(self.asset_id))
            session.add(exit_order(self.asset_id, exit_type="allocation", assigned_to="Example employee"))
            session.commit()
            stored = session.exec(text("SELECT count(*) FROM asset_entries")).scalar_one()  # type: ignore[call-overload]
        self.assertEqual(stored, 1)

    def test_sku_is_unique(self) -> None:
        self.assertRejected(asset(name="Other asset", office="Miami"))

    def test_quantity_must_be_positive(self) -> None:
        for quantity in (0, -1):
            with self.subTest(quantity=quantity):
                self.assertRejected(entry(self.asset_id, quantity=quantity))
                self.assertRejected(exit_order(self.asset_id, quantity=quantity))

    def test_vocabulary_is_closed(self) -> None:
        self.assertRejected(asset(sku="EXAMPLE-SKU-2", category="furniture"))
        self.assertRejected(asset(sku="EXAMPLE-SKU-3", office="Madrid"))
        self.assertRejected(entry(self.asset_id, office="valencia"))
        self.assertRejected(exit_order(self.asset_id, exit_type="loss"))

    def test_assigned_to_matches_exit_type(self) -> None:
        self.assertRejected(exit_order(self.asset_id, exit_type="allocation", assigned_to=None))
        self.assertRejected(exit_order(self.asset_id, exit_type="consumption", assigned_to="Example employee"))


class RowLevelSecurityTests(unittest.TestCase):
    def statements(self, url: str) -> list[str]:
        executed: list[str] = []
        engine = create_mock_engine(url, lambda sql, *args, **kwargs: executed.append(str(sql)))
        enable_row_level_security(engine)  # type: ignore[arg-type]
        return executed

    def test_postgresql_enables_rls_on_the_three_tables(self) -> None:
        self.assertEqual(
            self.statements("postgresql+psycopg2://"),
            [f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY" for name in ("assets", "asset_entries", "asset_exits")],
        )

    def test_sqlite_has_no_rls(self) -> None:
        self.assertEqual(self.statements("sqlite://"), [])

    def test_init_db_enables_rls_after_creating_the_tables(self) -> None:
        engine = build_engine(TEST_DATABASE_URL)
        self.addCleanup(engine.dispose)
        seen: list[set[str]] = []

        def spy(connection: Any) -> None:
            seen.append(set(inspect(connection).get_table_names()))

        with mock.patch.object(database, "enable_row_level_security", side_effect=spy):
            init_db(engine)
        self.assertEqual(len(seen), 1)
        self.assertTrue(INVENTORY_TABLE_NAMES <= seen[0])


class NoGlobalSessionTests(unittest.TestCase):
    SESSION_FACTORIES = {"Session", "sessionmaker", "scoped_session"}

    def calls(self, tree: ast.AST) -> list[ast.Call]:
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name | ast.Attribute)
            and (node.func.id if isinstance(node.func, ast.Name) else node.func.attr) in self.SESSION_FACTORIES
        ]

    def test_no_session_is_created_at_module_level(self) -> None:
        for path in sorted(APP_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for statement in tree.body:
                if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                    continue
                with self.subTest(file=path.relative_to(APP_DIR).as_posix(), line=statement.lineno):
                    self.assertEqual(self.calls(statement), [])

    def test_sessions_are_only_opened_inside_get_db(self) -> None:
        owners: list[str] = []
        for path in sorted(APP_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for function in ast.walk(tree):
                if isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef) and self.calls(function):
                    owners.append(f"{path.relative_to(APP_DIR).as_posix()}:{function.name}")
        self.assertEqual(owners, ["modules/inventory/database.py:get_db"])


class SpySession(Session):
    instances: list["SpySession"] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.closed = 0
        SpySession.instances.append(self)

    def close(self) -> None:
        self.closed += 1
        super().close()


def probe_app(tmp: str) -> FastAPI:
    app = create_app(inventory_settings(tmp))

    @app.get("/_probe/session")
    def probe(session: Session = Depends(get_db)) -> dict[str, int]:
        return {"session": id(session), "one": session.exec(text("SELECT 1")).scalar_one()}  # type: ignore[call-overload]

    return app


class GetDbTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        SpySession.instances = []
        patcher = mock.patch.object(database, "Session", SpySession)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(probe_app(tmp.name))

    def test_each_request_gets_its_own_session_and_it_is_closed(self) -> None:
        for _ in range(2):
            response = self.client.get("/_probe/session")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["one"], 1)
        self.assertEqual(len(SpySession.instances), 2)
        self.assertIsNot(SpySession.instances[0], SpySession.instances[1])
        self.assertEqual([session.closed for session in SpySession.instances], [1, 1])

    def test_session_is_closed_when_the_route_fails(self) -> None:
        @self.client.app.get("/_probe/fails")  # type: ignore[attr-defined]
        def fails(session: Session = Depends(get_db)) -> None:
            raise RuntimeError("boom")

        client = TestClient(self.client.app, raise_server_exceptions=False)
        self.assertEqual(client.get("/_probe/fails").status_code, 500)
        self.assertEqual([session.closed for session in SpySession.instances], [1])


def failing_route(error: Exception) -> Any:
    def failing(session: Session = Depends(get_db)) -> None:
        raise error

    return failing


class DatabaseUnavailableTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.app = create_app(inventory_settings(tmp.name))
        self.client = TestClient(self.app)

    def errors(self) -> list[Exception]:
        orig = Exception(f'connection to server at "{HOST}" failed: password for user "{USER}" ({SECRET})')
        return [
            OperationalError(f"SELECT * FROM assets WHERE sku = '{SECRET}'", {"sku": SECRET}, orig),
            InterfaceError(f"SELECT '{SECRET}'", {"value": SECRET}, orig),
            PoolTimeoutError(f"pool timeout for {POSTGRES_URL}"),
        ]

    def test_database_errors_respond_503_without_leaking_anything(self) -> None:
        for error in self.errors():
            with self.subTest(error=type(error).__name__):
                path = f"/_probe/{type(error).__name__}"
                self.app.add_api_route(path, failing_route(error))
                with capture_logs() as logs:
                    response = self.client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(
                    response.json(), {"detail": "storage is temporarily unavailable", "code": "storage_unavailable"}
                )
                assert_no_secrets(self, response.text)
                self.assertIn(f"storage inventory is unavailable: {type(error).__name__}", logs.text())
                assert_no_secrets(self, logs.text())
                self.assertNotIn("SELECT", logs.text())

    def test_other_database_errors_are_still_opaque_500s(self) -> None:
        @self.app.get("/_probe/integrity")
        def integrity(session: Session = Depends(get_db)) -> None:
            raise IntegrityError(f"INSERT '{SECRET}'", {"sku": SECRET}, Exception(SECRET))

        client = TestClient(self.app, raise_server_exceptions=False)
        with capture_logs() as logs:
            response = client.get("/_probe/integrity")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["code"], "internal_error")
        assert_no_secrets(self, response.text + logs.text())


class LifespanTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = inventory_settings(tmp.name)

    def test_startup_creates_the_tables(self) -> None:
        app = create_app(self.settings)
        with TestClient(app):
            tables = set(inspect(app.state.inventory_engine).get_table_names())
        self.assertTrue(INVENTORY_TABLE_NAMES <= tables)

    def test_existing_clients_without_lifespan_do_not_touch_the_database(self) -> None:
        app = create_app(self.settings)
        TestClient(app).get("/health")
        self.assertEqual(inspect(app.state.inventory_engine).get_table_names(), [])


if __name__ == "__main__":
    unittest.main()
