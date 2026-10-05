"""Tests for status.py: JSON schema, thresholds, graceful degradation."""

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from expense_tracker.models import Expense
from expense_tracker.status import (
    build_status,
    degraded_status,
    get_status_output,
    render_json,
    render_template,
)


def expense(expense_id, dollars, category="food", day="2026-03-05"):
    """Build an Expense from a dollar float *only* as test shorthand.

    The float never reaches production code: it is converted to exact cents
    here at the test boundary.
    """
    return Expense(id=expense_id, amount_cents=int(round(dollars * 100)),
                   category=category, date=day)


class TestStatusSchema(unittest.TestCase):
    def test_json_has_exact_keys(self):
        status = build_status([expense(1, 120.00)], {"2026-03": 50000}, date(2026, 3, 15))
        payload = json.loads(render_json(status))
        self.assertEqual(set(payload),
                         {"text", "tooltip", "month_total", "budget",
                          "percent", "state", "currency"})
        self.assertEqual(payload["month_total"], 120.00)
        self.assertEqual(payload["budget"], 500.00)
        self.assertEqual(payload["currency"], "₱")

    def test_json_without_budget_uses_null(self):
        status = build_status([expense(1, 10.00)], {}, date(2026, 3, 15))
        payload = json.loads(render_json(status))
        self.assertIsNone(payload["budget"])
        self.assertEqual(payload["state"], "ok")

    def test_tooltip_lists_month_and_categories(self):
        status = build_status([expense(1, 120.00, "food"), expense(2, 80.50, "transport")],
                              {}, date(2026, 3, 15))
        self.assertIn("March 2026", status["tooltip"])
        self.assertIn("Food: ₱120.00", status["tooltip"])

    def test_plain_text_with_and_without_budget(self):
        with_budget = build_status([expense(1, 120.00)], {"2026-03": 50000}, date(2026, 3, 15))
        self.assertIn("/", with_budget["text"])
        solo = build_status([expense(1, 120.00)], {}, date(2026, 3, 15))
        self.assertNotIn("/", solo["text"])


class TestStateThresholds(unittest.TestCase):
    def check(self, total, budget, expected):
        status = build_status([expense(1, total)], {"2026-03": int(budget * 100)},
                              date(2026, 3, 15))
        self.assertEqual(status["state"], expected)

    def test_ok_below_80_percent(self):
        self.check(79.90, 100, "ok")

    def test_warning_at_80_percent(self):
        self.check(80.00, 100, "warning")

    def test_warning_below_100(self):
        self.check(99.99, 100, "warning")

    def test_over_at_100_percent(self):
        self.check(100.00, 100, "over")

    def test_over_above_100(self):
        self.check(150.00, 100, "over")

    def test_ok_without_budget(self):
        status = build_status([expense(1, 9999.00)], {}, date(2026, 3, 15))
        self.assertEqual(status["state"], "ok")


class TestDegradation(unittest.TestCase):
    def test_missing_file_degrades_gracefully(self):
        with TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "nope.json")
            self.assertEqual(get_status_output(missing), "--")
            payload = json.loads(get_status_output(missing, as_json=True))
            self.assertEqual(payload["text"], "--")
            self.assertEqual(payload["state"], "ok")

    def test_corrupted_file_degrades_without_raising(self):
        with TemporaryDirectory() as tmp:
            bad = Path(tmp) / "expenses.json"
            bad.write_text("{ broken", encoding="utf-8")
            payload = json.loads(get_status_output(str(bad), as_json=True))
            self.assertEqual(payload["month_total"], 0.0)
            # Status must not back up or rewrite: read-only by design.
            self.assertFalse(bad.with_name(bad.name + ".bak").exists())

    def test_degraded_json_is_schema_valid(self):
        payload = json.loads(render_json(degraded_status()))
        self.assertEqual(set(payload),
                         {"text", "tooltip", "month_total", "budget",
                          "percent", "state", "currency"})

    def test_bad_template_falls_back_to_plain(self):
        status = build_status([], {}, date(2026, 3, 15))
        self.assertEqual(render_template(status, "{nonexistent}"), status["text"])


if __name__ == "__main__":
    unittest.main()
