"""Status bar output: fast, non-interactive, always valid.

The `status` command is polled by Quickshell every 60 s, so it must never
prompt, never write, and never exit nonzero just because data is missing.
Any read failure degrades to a safe placeholder instead of a traceback.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .models import CURRENCY, cents_to_str, compute_state, format_money  # noqa: F401 -- re-exported
from .storage import load_data, resolve_data_file


def month_label(today: date) -> str:
    """Human month title for tooltips, e.g. 'March 2026'."""
    return today.strftime("%B %Y")


def build_status(expenses: list, budgets: dict[str, int], today: date) -> dict:
    """Build the status dict for one month from in-memory rows.

    month_total/budget are JSON numbers (dollars); internal math stays in cents.
    """
    month_key = today.strftime("%Y-%m")
    month_rows = [e for e in expenses if e.date.startswith(month_key)]
    total_cents = sum(e.amount_cents for e in month_rows)
    budget_cents = budgets.get(month_key)
    has_budget = budget_cents is not None
    # State uses the exact ratio; only the displayed percent is rounded.
    # (Rounding first would flip 99.99% to 'over' via 100.0.)
    raw_percent = total_cents / budget_cents * 100 if has_budget and budget_cents else 0.0
    state = compute_state(raw_percent, has_budget)
    percent = round(raw_percent, 1)
    if has_budget and budget_cents is not None:
        text = f"{format_money(total_cents)} / {format_money(budget_cents)}"
    else:
        text = format_money(total_cents)
    tooltip = _build_tooltip(month_rows, total_cents, budget_cents, percent, today)
    return {
        "text": text,
        "tooltip": tooltip,
        "month_total": total_cents / 100,
        "budget": (budget_cents / 100) if has_budget and budget_cents is not None else None,
        "percent": percent,
        "state": state,
        "currency": CURRENCY,
    }


def _build_tooltip(
    month_rows: list, total_cents: int, budget_cents: int | None, percent: float, today: date
) -> str:
    lines = [month_label(today)]
    if not month_rows:
        lines.append("No expenses")
    else:
        grouped: dict[str, int] = {}
        for expense in month_rows:
            grouped[expense.category] = grouped.get(expense.category, 0) + expense.amount_cents
        for category in sorted(grouped, key=lambda c: (-grouped[c], c)):
            lines.append(f"{category.title()}: {format_money(grouped[category])}")
        lines.append(f"Total: {format_money(total_cents)}")
    if budget_cents is not None:
        lines.append(f"Budget: {format_money(budget_cents)} ({percent:.1f}%)")
    return "\n".join(lines)


def degraded_status() -> dict:
    """Safe placeholder when the data file is missing or unreadable."""
    return {
        "text": "--",
        "tooltip": "No data",
        "month_total": 0.0,
        "budget": None,
        "percent": 0.0,
        "state": "ok",
        "currency": CURRENCY,
    }


def render_plain(status: dict) -> str:
    """Single-line bar text."""
    return str(status.get("text", "--"))


def render_json(status: dict) -> str:
    """Schema-valid JSON for the Quickshell widget."""
    payload = {
        "text": str(status.get("text", "--")),
        "tooltip": str(status.get("tooltip", "")),
        "month_total": float(status.get("month_total", 0.0)),
        "budget": status.get("budget"),
        "percent": float(status.get("percent", 0.0)),
        "state": str(status.get("state", "ok")),
        "currency": str(status.get("currency", CURRENCY)),
    }
    if payload["budget"] is not None:
        payload["budget"] = float(payload["budget"])
    return json.dumps(payload, ensure_ascii=False)


def render_template(status: dict, template: str) -> str:
    """Expand a user template with status keys; fall back to plain text."""
    namespace = {
        "text": status.get("text", "--"),
        "tooltip": status.get("tooltip", ""),
        "month_total": cents_to_str(int(round(float(status.get("month_total", 0.0)) * 100))),
        "budget": (
            cents_to_str(int(round(float(status["budget"]) * 100)))
            if status.get("budget") is not None
            else ""
        ),
        "percent": f"{float(status.get('percent', 0.0)):.1f}",
        "state": status.get("state", "ok"),
        "currency": status.get("currency", CURRENCY),
    }
    try:
        return template.format(**namespace)
    except (KeyError, ValueError, AttributeError):
        return render_plain(status)


def get_status_output(
    data_file: str | Path | None = None,
    as_json: bool = False,
    template: str | None = None,
    today: date | None = None,
) -> str:
    """Read-only status fetch. Never raises, never writes, always returns text."""
    try:
        # Missing file degrades to '--' (distinct from an empty-but-present file).
        if not resolve_data_file(data_file).exists():
            status = degraded_status()
        else:
            _, store = load_data(data_file, backup=False)
            status = build_status(store.expenses, store.budgets, today or date.today())
    except Exception:  # noqa: BLE001 -- the bar must never see a traceback
        status = degraded_status()
    if as_json:
        return render_json(status)
    if template:
        return render_template(status, template)
    return render_plain(status)
