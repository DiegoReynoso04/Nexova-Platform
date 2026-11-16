import csv
import json
import os
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest import mock

from .support import REPO_ROOT, events_engine, insert_event, load_script

script = load_script()
DAY = date(2026, 10, 27)
UUIDS = [f"00000000-0000-4000-9000-{n:012d}" for n in range(1, 12)]


class AllowlistPartitionTests(unittest.TestCase):
    """La lista blanca no envejece en silencio: toda clave del plan está clasificada, y solo una vez."""

    def plan_keys(self):
        schemas = json.loads((REPO_ROOT / "docs" / "telemetry" / "event-schemas.json").read_text(encoding="utf-8"))
        keys: set[str] = set()
        for name, schema in schemas["definitions"].items():
            if name == "envelope":
                continue
            properties = schema.get("properties", {})
            tags = properties.get("properties") or properties.get("tags")
            keys |= set(tags["properties"] if tags and "properties" in tags else (tags or properties))
        return keys

    def test_lists_are_disjoint_and_cover_exactly_the_plan(self):
        exportable, excluded = script.EXPORTABLE_TAG_KEYS, script.EXCLUDED_TAG_KEYS
        self.assertEqual(exportable & excluded, set())
        self.assertEqual(exportable | excluded, self.plan_keys())
        self.assertEqual((len(exportable), len(excluded), len(self.plan_keys())), (88, 2, 90))

    def test_the_two_pseudonyms_are_excluded(self):
        self.assertEqual(script.EXCLUDED_TAG_KEYS, {"supplier_key", "target_user_id"})
        self.assertNotIn("supplier_key", script.EXPORTABLE_TAG_KEYS)
        self.assertNotIn("target_user_id", script.EXPORTABLE_TAG_KEYS)

    def test_columns_have_no_identifiers(self):
        self.assertEqual(script.CSV_COLUMNS, ("event_id", "event_type", "timestamp", "service", "schema_version", "tags"))

    def test_the_gitignore_covers_the_csv_and_its_temporary(self):
        text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("data/raw/telemetry_*.csv\n", text)
        self.assertIn("data/raw/telemetry_*.csv.part", text)


class FilterTagsTests(unittest.TestCase):
    def test_only_whitelisted_keys_survive(self):
        tags = {"office": "valencia", "supplier_key": "0" * 64, "target_user_id": UUIDS[0], "unknown_new_key": 1, "quantity": 3}
        self.assertEqual(script.filter_tags(tags), {"office": "valencia", "quantity": 3})

    def test_a_key_missing_from_both_lists_is_dropped_not_exported(self):
        self.assertEqual(script.filter_tags({"brand_new_key": "x"}), {})

    def test_tags_may_arrive_as_text_or_garbage(self):
        self.assertEqual(script.filter_tags('{"office": "miami", "supplier_key": "x"}'), {"office": "miami"})
        self.assertEqual(script.filter_tags(None), {})
        self.assertEqual(script.filter_tags([1, 2]), {})


class WriteCsvTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.path = self.dir / "telemetry_2026-10-27.csv"

    def row(self, n, tags=None):
        return {
            "event_id": UUIDS[n], "event_type": "page_viewed",
            "timestamp": datetime(2026, 10, 27, 9, 0, n, tzinfo=UTC), "service": "backoffice",
            "schema_version": "1.0.0", "tags": tags if tags is not None else {"office": "valencia"},
        }

    def read(self):
        with self.path.open(encoding="utf-8", newline="") as handle:
            return list(csv.reader(handle))

    def test_writes_header_and_rows_with_compact_sorted_tags_and_iso_utc(self):
        count = script.write_csv(self.path, [self.row(1, {"quantity": 2, "office": "miami", "supplier_key": "x"})])
        self.assertEqual(count, 1)
        header, record = self.read()
        self.assertEqual(header, list(script.CSV_COLUMNS))
        self.assertEqual(record[2], "2026-10-27T09:00:01+00:00")
        self.assertEqual(record[5], '{"office":"miami","quantity":2}')
        raw = self.path.read_bytes()
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", raw)

    def test_a_day_without_events_is_header_only(self):
        self.assertEqual(script.write_csv(self.path, []), 0)
        self.assertEqual(self.read(), [list(script.CSV_COLUMNS)])

    def test_a_failure_midway_leaves_no_final_file_and_no_part(self):
        def rows():
            yield self.row(1)
            raise RuntimeError("database went away")

        with self.assertRaises(RuntimeError):
            script.write_csv(self.path, rows())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_a_failure_in_the_rename_leaves_no_final_file(self):
        with mock.patch.object(os, "replace", side_effect=OSError("disk")), self.assertRaises(OSError):
            script.write_csv(self.path, [self.row(1)])
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_a_stale_part_from_a_dead_run_is_replaced_and_never_taken_for_the_result(self):
        (self.dir / (self.path.name + ".part")).write_text("partial garbage", encoding="utf-8")
        script.write_csv(self.path, [self.row(1)])
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), [self.path.name])
        self.assertNotIn("garbage", self.path.read_text(encoding="utf-8"))

    def test_creates_the_output_directory(self):
        nested = self.dir / "a" / "b" / "telemetry_2026-10-27.csv"
        script.write_csv(nested, [])
        self.assertTrue(nested.exists())


class ExportCsvTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.engine = events_engine()
        self.addCleanup(self.engine.dispose)

    def test_day_bounds_are_half_open_in_utc(self):
        insert_event(self.engine, UUIDS[0], datetime(2026, 10, 26, 23, 59, 59, 999999, tzinfo=UTC), {})
        insert_event(self.engine, UUIDS[1], datetime(2026, 10, 27, 0, 0, 0, tzinfo=UTC), {})
        insert_event(self.engine, UUIDS[2], datetime(2026, 10, 27, 23, 59, 59, 999999, tzinfo=UTC), {})
        insert_event(self.engine, UUIDS[3], datetime(2026, 10, 28, 0, 0, 0, tzinfo=UTC), {})
        path, rows = script.export_csv(self.engine, DAY, self.dir)
        self.assertEqual(rows, 2)
        ids = [r[0] for r in list(csv.reader(path.open(encoding="utf-8", newline="")))[1:]]
        self.assertEqual(ids, [UUIDS[1], UUIDS[2]])

    def test_order_is_timestamp_then_event_id(self):
        moment = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
        insert_event(self.engine, UUIDS[5], moment, {})
        insert_event(self.engine, UUIDS[4], moment, {})
        insert_event(self.engine, UUIDS[6], datetime(2026, 10, 27, 8, 0, tzinfo=UTC), {})
        path, _ = script.export_csv(self.engine, DAY, self.dir)
        ids = [r[0] for r in list(csv.reader(path.open(encoding="utf-8", newline="")))[1:]]
        self.assertEqual(ids, [UUIDS[6], UUIDS[4], UUIDS[5]])

    def test_identifiers_and_excluded_tags_never_reach_the_file(self):
        insert_event(
            self.engine, UUIDS[7], datetime(2026, 10, 27, 9, 0, tzinfo=UTC),
            {"office": "valencia", "supplier_key": "a" * 64, "target_user_id": UUIDS[9]},
            event_type="user_role_changed", user_id=UUIDS[8], session_id=UUIDS[10],
        )
        path, _ = script.export_csv(self.engine, DAY, self.dir)
        content = path.read_text(encoding="utf-8")
        for secret in ("a" * 64, UUIDS[8], UUIDS[9], UUIDS[10], "supplier_key", "target_user_id", "user_id", "session_id"):
            self.assertNotIn(secret, content)
        self.assertIn('{""office"":""valencia""}', content)

    def test_an_existing_file_is_never_touched_nor_the_database_read(self):
        path = script.csv_path(DAY, self.dir)
        path.write_text("keep me", encoding="utf-8")
        before = path.stat().st_mtime_ns
        with mock.patch.object(script, "fetch_rows", side_effect=AssertionError("must not query")):
            result_path, rows = script.export_csv(self.engine, DAY, self.dir)
        self.assertEqual((result_path, rows), (path, None))
        self.assertEqual(path.read_text(encoding="utf-8"), "keep me")
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_file_name(self):
        self.assertEqual(script.csv_path(DAY, self.dir).name, "telemetry_2026-10-27.csv")
        self.assertEqual(script.csv_path(DAY).parent, script.OUTPUT_DIR)
        self.assertEqual(script.OUTPUT_DIR, script.REPO_ROOT / "data" / "raw")
