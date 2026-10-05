"""Tests for cli.py: exit codes, stderr/stdout split, end-to-end flows."""

import io
import json
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory

from expense_tracker.cli import main


class CliCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_file = str(Path(self.tmp.name) / "expenses.json")

    def run_cli(self, *args):
        """Run main() capturing stdout/stderr; return (exit_code, out, err)."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--data-file", self.data_file, *args])
        return code, out.getvalue(), err.getvalue()


class TestCliExitCodes(CliCase):
    def test_add_then_list_end_to_end(self):
        code, out, _ = self.run_cli("add", "12.50", "food", "-d", "lunch")
        self.assertEqual(code, 0)
        self.assertIn("Added #1", out)
        code, out, _ = self.run_cli("list")
        self.assertEqual(code, 0)
        self.assertIn("food", out)
        self.assertIn("₱12.50", out)

    def test_add_negative_fails_with_code_2(self):
        code, out, err = self.run_cli("add", "-5", "food")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("Error:", err)

    def test_add_bad_category_fails_with_code_2(self):
        code, _, err = self.run_cli("add", "5", "###")
        self.assertEqual(code, 2)
        self.assertIn("Error:", err)

    def test_delete_unknown_id_fails_with_code_2(self):
        self.run_cli("add", "5", "food")
        code, _, err = self.run_cli("delete", "99")
        self.assertEqual(code, 2)
        self.assertIn("no expense with id 99", err)

    def test_corrupted_file_exits_1_with_backup(self):
        Path(self.data_file).parent.mkdir(parents=True, exist_ok=True)
        Path(self.data_file).write_text("{ broken", encoding="utf-8")
        code, out, err = self.run_cli("list")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("corrupted", err)
        backup = Path(self.data_file).with_name(Path(self.data_file).name + ".bak")
        self.assertTrue(backup.exists())

    def test_no_traceback_on_user_error(self):
        code, _, err = self.run_cli("add", "nan", "food")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


class TestCliCommands(CliCase):
    def test_summary_and_budget_flow(self):
        self.run_cli("add", "120.00", "food", "--date", "2026-03-05")
        code, out, _ = self.run_cli("summary", "--month", "2026-03")
        self.assertEqual(code, 0)
        self.assertIn("₱120.00", out)
        code, out, _ = self.run_cli("budget", "set", "500", "--month", "2026-03")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli("budget", "show", "--month", "2026-03")
        self.assertIn("₱120.00", out)
        self.assertIn("₱500.00", out)

    def test_edit_flow(self):
        self.run_cli("add", "10.00", "food")
        code, _, _ = self.run_cli("edit", "1", "--amount", "20.00")
        self.assertEqual(code, 0)
        _, out, _ = self.run_cli("list")
        self.assertIn("₱20.00", out)

    def test_export_flow(self):
        self.run_cli("add", "10.00", "food")
        dest = str(Path(self.tmp.name) / "out.csv")
        code, out, _ = self.run_cli("export", dest)
        self.assertEqual(code, 0)
        self.assertIn("Exported 1", out)

    def test_details_json_schema(self):
        self.run_cli("add", "10.00", "food", "--date", "2026-03-05")
        code, out, _ = self.run_cli("details", "--month", "2026-03", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(
            set(payload),
            {"month", "month_label", "total_cents", "count", "budget_cents",
             "percent", "state", "currency", "by_category", "recent"},
        )
        self.assertEqual(payload["total_cents"], 1000)

    def test_details_human_output(self):
        self.run_cli("add", "10.00", "food", "--date", "2026-03-05")
        code, out, _ = self.run_cli("details", "--month", "2026-03")
        self.assertEqual(code, 0)
        self.assertIn("March 2026", out)
        self.assertIn("₱10.00", out)

    def test_status_json_is_valid(self):
        self.run_cli("add", "10.00", "food")
        code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("state", payload)

    def test_status_missing_file_exits_zero(self):
        code, out, _ = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "--")


if __name__ == "__main__":
    unittest.main()
