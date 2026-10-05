"""Expense data model and input validation.

Money is stored as integer cents (never float) so totals are exact.
All parsing helpers raise ValidationError with a one-line message.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from .errors import ValidationError

MAX_CATEGORY_LEN = 30
MAX_DESCRIPTION_LEN = 200
# Letters, digits, spaces, and hyphens only (checked after trimming).
CATEGORY_RE = re.compile(r"^[A-Za-z0-9 \-]+$")
# App-wide display currency and budget-state thresholds (percent spent).
CURRENCY = "₱"
WARNING_AT = 80.0
OVER_AT = 100.0


def compute_state(percent: float, has_budget: bool) -> str:
    """Map a spent percentage to ok/warning/over."""
    if not has_budget or percent < WARNING_AT:
        return "ok"
    if percent < OVER_AT:
        return "warning"
    return "over"


def parse_amount_to_cents(value: str) -> int:
    """Parse a user-supplied amount like '12.50' into integer cents."""
    if isinstance(value, float):
        raise ValidationError("amount must not be a float; pass a string like '12.50'")
    if not isinstance(value, str):
        raise ValidationError(f"invalid amount: {value!r}")
    text = value.strip().lstrip("$₱").strip().replace(",", "")
    if not text:
        raise ValidationError("amount must be a positive number like '12.50'")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise ValidationError(f"invalid amount: {value!r}") from None
    if not amount.is_finite():
        raise ValidationError(f"invalid amount: {value!r}")
    if amount <= 0:
        raise ValidationError("amount must be greater than zero")
    # Decimal exponent tells us the number of decimal places: -2 means 2 dp.
    if amount.as_tuple().exponent < -2:
        raise ValidationError("amount must have at most 2 decimal places")
    return int(amount * 100)


def parse_category(value: str) -> str:
    """Trim, validate, and lowercase a category string."""
    if not isinstance(value, str):
        raise ValidationError("category must be a string")
    text = value.strip()
    if not text:
        raise ValidationError("category must not be empty")
    if len(text) > MAX_CATEGORY_LEN:
        raise ValidationError("category must be at most 30 characters")
    if not CATEGORY_RE.match(text):
        raise ValidationError("category may only contain letters, digits, spaces, and hyphens")
    return text.lower()


def parse_description(value: str | None) -> str:
    """Validate an optional description (empty string when omitted)."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValidationError("description must be a string")
    text = value.strip()
    if len(text) > MAX_DESCRIPTION_LEN:
        raise ValidationError("description must be at most 200 characters")
    return text


def parse_date(value: str | None) -> str:
    """Validate an ISO date, defaulting to today. Returns 'YYYY-MM-DD'."""
    today = date.today()
    if value is None or (isinstance(value, str) and not value.strip()):
        return today.isoformat()
    if not isinstance(value, str):
        raise ValidationError("date must look like YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValidationError(f"invalid date: {value!r} (expected YYYY-MM-DD)") from None
    # Allow a small clock-skew grace period, nothing more.
    if parsed > today_max_future(today):
        raise ValidationError("date must not be more than 1 day in the future")
    return parsed.isoformat()


def today_max_future(today: date) -> date:
    """Latest acceptable expense date (today + 1 day)."""
    from datetime import timedelta

    return today + timedelta(days=1)


def parse_month(value: str) -> str:
    """Validate a 'YYYY-MM' month string and return it normalized."""
    if not isinstance(value, str):
        raise ValidationError("month must look like YYYY-MM")
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m").date()
    except ValueError:
        raise ValidationError(f"invalid month: {value!r} (expected YYYY-MM)") from None
    return parsed.strftime("%Y-%m")


def cents_to_str(cents: int) -> str:
    """Format cents as '12.50' without a currency symbol."""
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100}.{cents % 100:02d}"


def format_money(cents: int, currency: str = CURRENCY) -> str:
    """Format cents as '₱12.50'."""
    return f"{currency}{cents_to_str(cents)}"


@dataclass
class Expense:
    """One expense row. Amount is integer cents; date is ISO 'YYYY-MM-DD'."""

    id: int
    amount_cents: int
    category: str
    description: str = ""
    date: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, int) or self.id <= 0:
            raise ValidationError("expense id must be a positive integer")
        if not isinstance(self.amount_cents, int) or self.amount_cents <= 0:
            raise ValidationError("expense amount must be a positive integer number of cents")
        # Reuse the same validators so programmatic construction matches CLI input.
        object.__setattr__(self, "category", parse_category(self.category))
        object.__setattr__(self, "description", parse_description(self.description))
        # parse_date(None) defaults to today; here an empty date means "fill today".
        object.__setattr__(self, "date", parse_date(self.date or None))

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict."""
        return {
            "id": self.id,
            "amount_cents": self.amount_cents,
            "category": self.category,
            "description": self.description,
            "date": self.date,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Expense":
        """Deserialize from a dict, raising ValidationError on bad data."""
        if not isinstance(data, dict):
            raise ValidationError("expense entry must be an object")
        try:
            return cls(
                id=int(data["id"]),
                amount_cents=int(data["amount_cents"]),
                category=str(data["category"]),
                description=str(data.get("description", "")),
                date=str(data["date"]),
            )
        except KeyError as exc:
            raise ValidationError(f"expense entry is missing {exc}") from None
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"invalid expense entry: {exc}") from None
