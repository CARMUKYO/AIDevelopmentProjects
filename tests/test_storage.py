"""Tests for storage.py: paths, atomic writes, corruption backup."""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from expense_tracker.errors import StorageError
from expense_tracker.models import Expense
from expense_tracker.storage import (
    SCHEMA_VERSION,
    StoreData,
    get_default_data_file,
    load_data,
    save_data,
)


class TestDataFileResolution(unittest.TestCase):
    def test_uses_xdg_data_home(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/tmp/xdgtest"}):
            self.assertEqual(
                get_default_data_file(),
                Path("/tmp/xdgtest/expense-tracker/expenses.json"),
            )

    def test_falls_back_to_home(self):
        with patch.dict(os.environ, {}, clear=True):
            path = get_default_data_file()
        self.assertTrue(str(path).endswith(".local/share/expense-tracker/expenses.json"))


class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_file = Path(self.tmp.name) / "sub" / "expenses.json"

    def test_missing_file_returns_empty_store(self):
        path, store = load_data(self.data_file)
        self.assertEqual(path, self.data_file)
        self.assertEqual(store.expenses, [])
        self.assertEqual(store.next_id, 1)
        self.assertEqual(store.budgets, {})

    def test_round_trip_preserves_data(self):
        store = StoreData(
            expenses=[Expense(id=1, amount_cents=1250, category="food", date="2026-03-01")],
            next_id=2,
            budgets={"2026-03": 50000},
        )
        save_data(self.data_file, store)
        _, loaded = load_data(self.data_file)
        self.assertEqual(loaded, store)

    def test_save_writes_schema_version(self):
        save_data(self.data_file, StoreData())
        payload = json.loads(self.data_file.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], SCHEMA_VERSION)

    def test_save_creates_parent_dirs(self):
        save_data(self.data_file, StoreData())
        self.assertTrue(self.data_file.exists())

    def test_corrupted_file_backs_up_and_raises(self):
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text("{ not valid json", encoding="utf-8")
        with self.assertRaises(StorageError):
            load_data(self.data_file)
        backup = self.data_file.with_name(self.data_file.name + ".bak")
        self.assertTrue(backup.exists())
        # Original is left untouched so no data is lost.
        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "{ not valid json")

    def test_corrupted_schema_backs_up(self):
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text('{"schema_version": 999}', encoding="utf-8")
        with self.assertRaises(StorageError):
            load_data(self.data_file)
        self.assertTrue(self.data_file.with_name(self.data_file.name + ".bak").exists())

    def test_atomic_write_leaves_no_temp_files(self):
        save_data(self.data_file, StoreData(next_id=5))
        leftovers = list(self.data_file.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])
        _, loaded = load_data(self.data_file)
        self.assertEqual(loaded.next_id, 5)

    def test_failed_write_does_not_corrupt_existing(self):
        save_data(self.data_file, StoreData(next_id=3))
        before = self.data_file.read_text(encoding="utf-8")
        with patch("expense_tracker.storage.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(StorageError):
                save_data(self.data_file, StoreData(next_id=99))
        self.assertEqual(self.data_file.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
