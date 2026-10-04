"""Business logic: add, delete, edit, filter, summarize, export, budgets.

The service owns the in-memory StoreData and saves after each mutation,
so the CLI stays thin and tests can use temporary data files.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from .errors import ExpenseNotFoundError, StorageError, ValidationError
from .models import (
    CURRENCY,
    Expense,
    cents_to_str,
    compute_state,
    parse_amount_to_cents,
    parse_category,
    parse_date,
    parse_description,
    parse_month,
)
from .storage import StoreData, load_data, save_data

VALID_SORTS = ("date", "amount")


class ExpenseService:
    """Loads the store once; each mutating method persists immediately."""

    def __init__(self, data_file: str | Path | None = None) -> None:
        self._path, self._store = load_data(data_file)

    @property
    def data_file(self) -> Path:
        """Filesystem path backing this service."""
        return self._path

    @property
    def store(self) -> StoreData:
        """Direct store access for read-only helpers (status, tests)."""
        return self._store

    def _save(self) -> None:
        save_data(self._path, self._store)

    def _find(self, expense_id: int) -> Expense:
        for expense in self._store.expenses:
            if expense.id == expense_id:
                return expense
        raise ExpenseNotFoundError(f"no expense with id {expense_id}")

    def add(
        self,
        amount: str,
        category: str,
        description: str | None = None,
        date_str: str | None = None,
    ) -> Expense:
        """Validate fields, assign the smallest free ID, persist, return the row."""
        expense = Expense(
            id=self._smallest_free_id(),
            amount_cents=parse_amount_to_cents(amount),
            category=parse_category(category),
            description=parse_description(description),
            date=parse_date(date_str),
        )
        self._store.expenses.append(expense)
        # Keep next_id above every used ID so old files stay consistent.
        self._store.next_id = max(e.id for e in self._store.expenses) + 1
        self._save()
        return expense

    def _smallest_free_id(self) -> int:
        """Lowest positive ID not currently in use (deleted IDs are recycled)."""
        used = {e.id for e in self._store.expenses}
        candidate = 1
        while candidate in used:
            candidate += 1
        return candidate

    def delete(self, expense_id: int) -> Expense:
        """Remove one row by ID and persist."""
        expense = self._find(_coerce_id(expense_id))
        self._store.expenses = [e for e in self._store.expenses if e.id != expense.id]
        self._save()
        return expense

    def edit(
        self,
        expense_id: int,
        amount: str | None = None,
        category: str | None = None,
        description: str | None = None,
        date_str: str | None = None,
    ) -> Expense:
        """Update only the supplied fields, then persist."""
        if amount is None and category is None and description is None and date_str is None:
            raise ValidationError("edit needs at least one of --amount/--category/--description/--date")
        expense = self._find(_coerce_id(expense_id))
        if amount is not None:
            expense.amount_cents = parse_amount_to_cents(amount)
        if category is not None:
            expense.category = parse_category(category)
        if description is not None:
            expense.description = parse_description(description)
        if date_str is not None:
            expense.date = parse_date(date_str)
        self._save()
        return expense

    def list_expenses(
        self,
        category: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        sort: str | None = None,
    ) -> list[Expense]:
        """Filter by category/date range, then sort."""
        wanted = parse_category(category) if category else None
        start = parse_date(from_date) if from_date else None
        end = parse_date(to_date) if to_date else None
        if start and end and start > end:
            raise ValidationError("--from must not be after --to")
        if sort is not None and sort not in VALID_SORTS:
            raise ValidationError("--sort must be 'date' or 'amount'")
        rows = [
            e
            for e in self._store.expenses
            if (wanted is None or e.category == wanted)
            and (start is None or e.date >= start)
            and (end is None or e.date <= end)
        ]
        if sort == "amount":
            rows.sort(key=lambda e: (e.amount_cents, e.id))
        else:  # default and 'date': chronological, stable by id
            rows.sort(key=lambda e: (e.date, e.id))
        return rows

    def summarize(self, month: str | None = None, by_category: bool = False) -> dict:
        """Total cents and count, optionally for one month and/or grouped."""
        wanted_month = parse_month(month) if month else None
        rows = self._store.expenses
        if wanted_month:
            rows = [e for e in rows if e.date.startswith(wanted_month)]
        total = sum(e.amount_cents for e in rows)
        result: dict = {"total_cents": total, "count": len(rows), "month": wanted_month}
        if by_category:
            grouped: dict[str, int] = {}
            for expense in rows:
                grouped[expense.category] = grouped.get(expense.category, 0) + expense.amount_cents
            result["by_category"] = dict(sorted(grouped.items()))
        return result

    def details(self, month: str | None = None, recent_limit: int = 8) -> dict:
        """Month detail blob for panels: totals, budget state, categories, recents.

        Amounts stay integer cents (exact); display formatting is the caller's job.
        """
        target = parse_month(month) if month else date.today().strftime("%Y-%m")
        rows = [e for e in self._store.expenses if e.date.startswith(target)]
        total = sum(e.amount_cents for e in rows)
        budget = self._store.budgets.get(target)
        raw_percent = total / budget * 100 if budget else 0.0
        grouped: dict[str, int] = {}
        for expense in rows:
            grouped[expense.category] = grouped.get(expense.category, 0) + expense.amount_cents
        by_category = [
            {"category": cat, "label": cat.title(), "total_cents": grouped[cat]}
            for cat in sorted(grouped, key=lambda c: (-grouped[c], c))
        ]
        recent = sorted(rows, key=lambda e: (e.date, e.id), reverse=True)[:recent_limit]
        return {
            "month": target,
            "month_label": _month_label(target),
            "total_cents": total,
            "count": len(rows),
            "budget_cents": budget,
            "percent": round(raw_percent, 1),
            "state": compute_state(raw_percent, budget is not None),
            "currency": CURRENCY,
            "by_category": by_category,
            "recent": [
                {
                    "id": e.id,
                    "date": e.date,
                    "category": e.category,
                    "label": e.category.title(),
                    "description": e.description,
                    "amount_cents": e.amount_cents,
                }
                for e in recent
            ],
        }

    def export(self, path: str | Path, fmt: str | None = None) -> int:
        """Write expenses to CSV or JSON. Returns the row count."""
        dest = Path(path).expanduser()
        fmt = _resolve_export_format(dest, fmt)
        rows = sorted(self._store.expenses, key=lambda e: e.id)
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if fmt == "csv":
                _write_csv(dest, rows)
            else:
                _write_json(dest, rows)
        except OSError as exc:
            raise StorageError(f"could not export to {dest}: {exc}") from None
        return len(rows)

    def budget_set(self, amount: str, month: str | None = None) -> tuple[str, int]:
        """Set the monthly budget (cents) for the given or current month."""
        target = parse_month(month) if month else date.today().strftime("%Y-%m")
        cents = parse_amount_to_cents(amount)
        self._store.budgets[target] = cents
        self._save()
        return target, cents

    def budget_show(self, month: str | None = None) -> dict:
        """Show one month's budget (default: current month)."""
        target = parse_month(month) if month else date.today().strftime("%Y-%m")
        budgeted = self._store.budgets.get(target)
        spent = sum(e.amount_cents for e in self._store.expenses if e.date.startswith(target))
        return {"month": target, "budget_cents": budgeted, "spent_cents": spent}

    def all_budgets(self) -> dict[str, int]:
        """All budgets sorted by month (used by 'budget show --all')."""
        return dict(sorted(self._store.budgets.items()))


def _month_label(month_key: str) -> str:
    """Turn 'YYYY-MM' into 'Month YYYY' (input already validated)."""
    return date(int(month_key[:4]), int(month_key[5:7]), 1).strftime("%B %Y")


def _coerce_id(expense_id: object) -> int:
    """Accept int or numeric string IDs; reject everything else."""
    if isinstance(expense_id, int) and expense_id > 0:
        return expense_id
    if isinstance(expense_id, str) and expense_id.strip().isdigit() and int(expense_id) > 0:
        return int(expense_id)
    raise ValidationError(f"invalid id: {expense_id!r}")


def _resolve_export_format(dest: Path, fmt: str | None) -> str:
    if fmt is None:
        fmt = "json" if dest.suffix.lower() == ".json" else "csv"
    fmt = fmt.lower()
    if fmt not in ("csv", "json"):
        raise ValidationError("--format must be 'csv' or 'json'")
    return fmt


def _write_csv(dest: Path, rows: list[Expense]) -> None:
    with dest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "date", "category", "amount", "description"])
        for expense in rows:
            writer.writerow(
                [expense.id, expense.date, expense.category,
                 cents_to_str(expense.amount_cents), expense.description]
            )


def _write_json(dest: Path, rows: list[Expense]) -> None:
    import json

    payload = [
        {
            "id": e.id,
            "date": e.date,
            "category": e.category,
            "amount": cents_to_str(e.amount_cents),
            "description": e.description,
        }
        for e in rows
    ]
    with dest.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
