"""Tests for models.py: amount/category/date/description validation."""

import unittest
from datetime import date, timedelta

from expense_tracker.errors import ValidationError
from expense_tracker.models import (
    Expense,
    cents_to_str,
    format_money,
    parse_amount_to_cents,
    parse_category,
    parse_date,
    parse_description,
)


class TestParseAmount(unittest.TestCase):
    def test_valid_amounts(self):
        self.assertEqual(parse_amount_to_cents("12.50"), 1250)
        self.assertEqual(parse_amount_to_cents("12"), 1200)
        self.assertEqual(parse_amount_to_cents("0.01"), 1)
        self.assertEqual(parse_amount_to_cents("  $12.50  "), 1250)
        self.assertEqual(parse_amount_to_cents("₱12.50"), 1250)

    def test_add_rejects_negative_amount(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("-5")

    def test_add_rejects_zero_amount(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("0")

    def test_add_rejects_three_decimals(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("12.505")

    def test_add_rejects_nan(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("nan")

    def test_add_rejects_inf(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("inf")
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("-inf")

    def test_add_rejects_non_numeric(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents("lunch")

    def test_add_rejects_float_input(self):
        with self.assertRaises(ValidationError):
            parse_amount_to_cents(12.50)  # type: ignore[arg-type]


class TestParseCategory(unittest.TestCase):
    def test_normalizes_case_and_whitespace(self):
        self.assertEqual(parse_category("  Food  "), "food")

    def test_rejects_empty_category(self):
        with self.assertRaises(ValidationError):
            parse_category("   ")

    def test_rejects_long_category(self):
        with self.assertRaises(ValidationError):
            parse_category("x" * 31)

    def test_rejects_bad_characters(self):
        with self.assertRaises(ValidationError):
            parse_category("food & drink")

    def test_accepts_hyphen_digits_spaces(self):
        self.assertEqual(parse_category("Meal-2 Go"), "meal-2 go")


class TestParseDate(unittest.TestCase):
    def test_defaults_to_today(self):
        self.assertEqual(parse_date(None), date.today().isoformat())

    def test_accepts_valid_iso_date(self):
        self.assertEqual(parse_date("2026-03-15"), "2026-03-15")

    def test_rejects_malformed_date(self):
        with self.assertRaises(ValidationError):
            parse_date("03/15/2026")
        with self.assertRaises(ValidationError):
            parse_date("2026-13-01")
        with self.assertRaises(ValidationError):
            parse_date("not-a-date")

    def test_rejects_far_future_date(self):
        far = (date.today() + timedelta(days=2)).isoformat()
        with self.assertRaises(ValidationError):
            parse_date(far)

    def test_allows_tomorrow(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(parse_date(tomorrow), tomorrow)


class TestParseDescription(unittest.TestCase):
    def test_none_becomes_empty(self):
        self.assertEqual(parse_description(None), "")

    def test_rejects_long_description(self):
        with self.assertRaises(ValidationError):
            parse_description("x" * 201)


class TestExpenseDataclass(unittest.TestCase):
    def test_round_trip_to_dict(self):
        expense = Expense(id=1, amount_cents=1250, category="Food",
                          description="lunch", date="2026-03-15")
        restored = Expense.from_dict(expense.to_dict())
        self.assertEqual(restored, expense)

    def test_from_dict_rejects_missing_keys(self):
        with self.assertRaises(ValidationError):
            Expense.from_dict({"id": 1})

    def test_money_formatting(self):
        self.assertEqual(cents_to_str(1250), "12.50")
        self.assertEqual(format_money(1250), "₱12.50")


if __name__ == "__main__":
    unittest.main()
