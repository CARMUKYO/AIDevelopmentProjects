"""Tests for service.py: add/edit/delete, filters, summary math, budgets."""

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from expense_tracker.errors import ExpenseNotFoundError, ValidationError
from expense_tracker.service import ExpenseService


class ServiceCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_file = str(Path(self.tmp.name) / "expenses.json")
        self.svc = ExpenseService(data_file=self.data_file)

    def add(self, amount="10.00", category="food", **kwargs):
        return self.svc.add(amount, category, **kwargs)


class TestAddEditDelete(ServiceCase):
    def test_add_assigns_incrementing_ids(self):
        first = self.add("5.00", "food")
        second = self.add("7.50", "transport")
        self.assertEqual((first.id, second.id), (1, 2))

    def test_deleted_ids_are_reused(self):
        self.add()
        self.add()
        self.svc.delete(1)
        third = self.add()
        self.assertEqual(third.id, 1)

    def test_reuse_picks_smallest_free_id(self):
        self.add()
        self.add()
        self.add()
        self.svc.delete(2)
        reused = self.add()
        self.assertEqual(reused.id, 2)
        # With no gaps, allocation continues past the max ID.
        self.assertEqual(self.add().id, 4)

    def test_delete_removes_row(self):
        self.add()
        deleted = self.svc.delete(1)
        self.assertEqual(deleted.id, 1)
        self.assertEqual(self.svc.list_expenses(), [])

    def test_delete_unknown_id_raises(self):
        with self.assertRaises(ExpenseNotFoundError):
            self.svc.delete(99)

    def test_edit_unknown_id_raises(self):
        with self.assertRaises(ExpenseNotFoundError):
            self.svc.edit(99, amount="5.00")

    def test_edit_updates_only_given_fields(self):
        expense = self.add("10.00", "food", description="a", date_str="2026-03-01")
        updated = self.svc.edit(expense.id, amount="20.00")
        self.assertEqual(updated.amount_cents, 2000)
        self.assertEqual(updated.category, "food")
        self.assertEqual(updated.description, "a")

    def test_edit_with_no_fields_raises(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.svc.edit(1)

    def test_edit_rejects_bad_amount(self):
        self.add()
        with self.assertRaises(ValidationError):
            self.svc.edit(1, amount="-3")


class TestFilteringSorting(ServiceCase):
    def setUp(self):
        super().setUp()
        self.add("30.00", "food", date_str="2026-03-10")
        self.add("10.00", "transport", date_str="2026-03-01")
        self.add("20.00", "food", date_str="2026-04-01")

    def test_filter_by_category(self):
        rows = self.svc.list_expenses(category="FOOD")
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(e.category == "food" for e in rows))

    def test_filter_by_date_range(self):
        rows = self.svc.list_expenses(from_date="2026-03-01", to_date="2026-03-31")
        self.assertEqual(len(rows), 2)

    def test_from_after_to_raises(self):
        with self.assertRaises(ValidationError):
            self.svc.list_expenses(from_date="2026-04-01", to_date="2026-03-01")

    def test_sort_by_amount_ascending(self):
        rows = self.svc.list_expenses(sort="amount")
        self.assertEqual([e.amount_cents for e in rows], [1000, 2000, 3000])

    def test_sort_by_date_default(self):
        rows = self.svc.list_expenses(sort="date")
        self.assertEqual([e.date for e in rows],
                         ["2026-03-01", "2026-03-10", "2026-04-01"])


class TestSummaryMath(ServiceCase):
    def test_summary_has_no_float_rounding_errors(self):
        # 0.10 + 0.20 must be exactly 0.30; float would give 0.30000000000000004.
        self.add("0.10", "food", date_str="2026-03-01")
        self.add("0.20", "food", date_str="2026-03-02")
        result = self.svc.summarize()
        self.assertEqual(result["total_cents"], 30)
        self.assertEqual(result["count"], 2)

    def test_summary_filters_by_month(self):
        self.add("10.00", "food", date_str="2026-03-01")
        self.add("99.00", "food", date_str="2026-04-01")
        result = self.svc.summarize(month="2026-03")
        self.assertEqual(result["total_cents"], 1000)

    def test_summary_groups_by_category(self):
        self.add("10.00", "food", date_str="2026-03-01")
        self.add("5.00", "transport", date_str="2026-03-02")
        result = self.svc.summarize(by_category=True)
        self.assertEqual(result["by_category"], {"food": 1000, "transport": 500})

    def test_summary_rejects_bad_month(self):
        with self.assertRaises(ValidationError):
            self.svc.summarize(month="march")


class TestDetails(ServiceCase):
    def test_details_blob_shape(self):
        self.add("120.00", "food", description="lunch", date_str="2026-03-05")
        self.add("80.50", "transport", date_str="2026-03-06")
        self.svc.budget_set("500", "2026-03")
        info = self.svc.details("2026-03")
        self.assertEqual(info["month"], "2026-03")
        self.assertEqual(info["month_label"], "March 2026")
        self.assertEqual(info["total_cents"], 20050)
        self.assertEqual(info["count"], 2)
        self.assertEqual(info["budget_cents"], 50000)
        self.assertEqual(info["state"], "ok")
        self.assertEqual(info["currency"], "₱")
        self.assertEqual([c["category"] for c in info["by_category"]], ["food", "transport"])
        self.assertEqual(len(info["recent"]), 2)
        # Most recent first.
        self.assertEqual(info["recent"][0]["date"], "2026-03-06")

    def test_details_without_budget_has_null_budget(self):
        self.add("10.00", "food", date_str="2026-03-01")
        info = self.svc.details("2026-03")
        self.assertIsNone(info["budget_cents"])
        self.assertEqual(info["state"], "ok")

    def test_details_rejects_bad_month(self):
        with self.assertRaises(ValidationError):
            self.svc.details("march")


class TestExportBudget(ServiceCase):
    def test_export_csv_contents(self):
        self.add("12.50", "food", description="lunch", date_str="2026-03-01")
        dest = Path(self.tmp.name) / "out.csv"
        count = self.svc.export(dest, "csv")
        self.assertEqual(count, 1)
        with dest.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(rows[0]["amount"], "12.50")
        self.assertEqual(rows[0]["category"], "food")

    def test_export_json_contents(self):
        self.add("12.50", "food", date_str="2026-03-01")
        dest = Path(self.tmp.name) / "out.json"
        self.svc.export(dest, None)  # format inferred from suffix
        payload = json.loads(dest.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["amount"], "12.50")

    def test_budget_set_and_show(self):
        self.add("120.00", "food", date_str="2026-03-05")
        month, cents = self.svc.budget_set("500", "2026-03")
        self.assertEqual((month, cents), ("2026-03", 50000))
        info = self.svc.budget_show("2026-03")
        self.assertEqual(info["spent_cents"], 12000)
        self.assertEqual(info["budget_cents"], 50000)


if __name__ == "__main__":
    unittest.main()
