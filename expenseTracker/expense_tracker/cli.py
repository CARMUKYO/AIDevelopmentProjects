"""argparse CLI: parses input, delegates to the service, maps errors to exits.

Exit codes: 0 success, 1 runtime/storage error, 2 usage/validation error.
Normal output goes to stdout; errors go to stderr as a single line.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .errors import ExpenseTrackerError, StorageError, ValidationError
from .models import format_money
from .service import ExpenseService
from .status import get_status_output


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level parser with global flags and subcommands."""
    parser = argparse.ArgumentParser(prog="expense", description="Track expenses from the terminal.")
    parser.add_argument("--data-file", metavar="PATH", default=None, help="Override storage location.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add = sub.add_parser("add", help="Add an expense.")
    add.add_argument("amount", help="Amount like 12.50 (positive, max 2 decimals).")
    add.add_argument("category", help="Category (letters, digits, spaces, hyphens).")
    add.add_argument("-d", "--description", default=None, help="Optional note (max 200 chars).")
    add.add_argument("--date", default=None, help="Date YYYY-MM-DD (default: today).")

    listing = sub.add_parser("list", help="List expenses in a table.")
    listing.add_argument("--category", default=None, help="Filter by category.")
    listing.add_argument("--from", dest="from_date", default=None, help="Start date YYYY-MM-DD.")
    listing.add_argument("--to", dest="to_date", default=None, help="End date YYYY-MM-DD.")
    listing.add_argument("--sort", choices=["date", "amount"], default=None, help="Sort key.")

    delete = sub.add_parser("delete", help="Delete an expense by ID.")
    delete.add_argument("id", help="Expense ID.")

    edit = sub.add_parser("edit", help="Update fields of one expense.")
    edit.add_argument("id", help="Expense ID.")
    edit.add_argument("--amount", default=None, help="New amount.")
    edit.add_argument("--category", default=None, help="New category.")
    edit.add_argument("--description", default=None, help="New description.")
    edit.add_argument("--date", default=None, help="New date YYYY-MM-DD.")

    summary = sub.add_parser("summary", help="Show totals, optionally grouped.")
    summary.add_argument("--month", default=None, help="Month YYYY-MM.")
    summary.add_argument("--by", dest="by", choices=["category"], default=None, help="Group by category.")

    export = sub.add_parser("export", help="Export expenses to CSV or JSON.")
    export.add_argument("path", help="Destination file.")
    export.add_argument("--format", dest="fmt", choices=["csv", "json"], default=None)

    details = sub.add_parser("details", help="Month details: totals, categories, recent.")
    details.add_argument("--month", default=None, help="Month YYYY-MM (default: current).")
    details.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    budget = sub.add_parser("budget", help="Monthly budgets.")
    budget_sub = budget.add_subparsers(dest="budget_cmd", required=True, metavar="BUDGET_CMD")
    bset = budget_sub.add_parser("set", help="Set a monthly budget.")
    bset.add_argument("amount", help="Budget amount like 500.")
    bset.add_argument("--month", default=None, help="Month YYYY-MM (default: current).")
    bshow = budget_sub.add_parser("show", help="Show budget status.")
    bshow.add_argument("--month", default=None, help="Month YYYY-MM (default: current).")
    bshow.add_argument("--all", action="store_true", help="Show all months with budgets.")

    status = sub.add_parser("status", help="Compact status bar output.")
    status.add_argument("--json", action="store_true", help="Emit schema-valid JSON.")
    status.add_argument("--format", dest="template", default=None, help="Custom template.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point returning an exit code (no sys.exit here for testability)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except ValidationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except StorageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ExpenseTrackerError as exc:  # any other expected failure
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def console_main() -> None:
    """Console-script wrapper that turns the return code into a real exit."""
    raise SystemExit(main())


def _service(args: argparse.Namespace) -> ExpenseService:
    return ExpenseService(data_file=args.data_file)


def _dispatch(args: argparse.Namespace) -> int:
    handlers = {
        "add": _handle_add,
        "list": _handle_list,
        "delete": _handle_delete,
        "edit": _handle_edit,
        "summary": _handle_summary,
        "export": _handle_export,
        "details": _handle_details,
        "budget": _handle_budget,
        "status": _handle_status,
    }
    return handlers[args.command](args)


def _handle_add(args: argparse.Namespace) -> int:
    expense = _service(args).add(args.amount, args.category, args.description, args.date)
    print(f"Added #{expense.id}: {format_money(expense.amount_cents)} {expense.category} ({expense.date})")
    return 0


def _handle_list(args: argparse.Namespace) -> int:
    rows = _service(args).list_expenses(args.category, args.from_date, args.to_date, args.sort)
    if not rows:
        print("No expenses.")
        return 0
    widths = _column_widths(rows)
    header = f"{'ID':>{widths[0]}}  {'Date':<{widths[1]}}  {'Category':<{widths[2]}}  {'Amount':>{widths[3]}}  Description"
    print(header)
    print("-" * len(header))
    for expense in rows:
        print(
            f"{expense.id:>{widths[0]}}  {expense.date:<{widths[1]}}  "
            f"{expense.category:<{widths[2]}}  "
            f"{format_money(expense.amount_cents):>{widths[3]}}  {expense.description}"
        )
    total = sum(e.amount_cents for e in rows)
    print(f"\nTotal: {format_money(total)} ({len(rows)} expenses)")
    return 0


def _column_widths(rows: list) -> tuple[int, int, int, int]:
    """Size table columns from the data so output stays aligned."""
    id_w = max([len("ID")] + [len(str(e.id)) for e in rows])
    date_w = max([len("Date")] + [len(e.date) for e in rows])
    cat_w = max([len("Category")] + [len(e.category) for e in rows])
    amt_w = max([len("Amount")] + [len(format_money(e.amount_cents)) for e in rows])
    return id_w, date_w, cat_w, amt_w


def _handle_delete(args: argparse.Namespace) -> int:
    expense = _service(args).delete(args.id)
    print(f"Deleted #{expense.id}.")
    return 0


def _handle_edit(args: argparse.Namespace) -> int:
    expense = _service(args).edit(args.id, args.amount, args.category, args.description, args.date)
    print(f"Updated #{expense.id}.")
    return 0


def _handle_summary(args: argparse.Namespace) -> int:
    result = _service(args).summarize(args.month, by_category=(args.by == "category"))
    label = f" ({result['month']})" if result["month"] else ""
    print(f"Total{label}: {format_money(result['total_cents'])} ({result['count']} expenses)")
    for category, cents in result.get("by_category", {}).items():
        print(f"  {category}: {format_money(cents)}")
    return 0


def _handle_export(args: argparse.Namespace) -> int:
    count = _service(args).export(args.path, args.fmt)
    print(f"Exported {count} expenses to {Path(args.path).expanduser()}.")
    return 0


def _handle_details(args: argparse.Namespace) -> int:
    info = _service(args).details(args.month)
    if args.json:
        import json

        print(json.dumps(info, ensure_ascii=False))
        return 0
    if info["budget_cents"] is None:
        print(f"{info['month_label']}: {format_money(info['total_cents'])} ({info['count']} expenses)")
    else:
        print(
            f"{info['month_label']}: {format_money(info['total_cents'])} / "
            f"{format_money(info['budget_cents'])} ({info['percent']:.1f}%)"
        )
    for row in info["by_category"]:
        print(f"  {row['label']}: {format_money(row['total_cents'])}")
    if info["recent"]:
        print("Recent:")
        for item in info["recent"]:
            note = f"  {item['description']}" if item["description"] else ""
            print(f"  {item['date']}  {item['label']:<12} {format_money(item['amount_cents']):>10}{note}")
    return 0


def _handle_budget(args: argparse.Namespace) -> int:
    service = _service(args)
    if args.budget_cmd == "set":
        month, cents = service.budget_set(args.amount, args.month)
        print(f"Budget for {month}: {format_money(cents)}")
        return 0
    if args.all:
        budgets = service.all_budgets()
        if not budgets:
            print("No budgets set.")
            return 0
        for month, cents in budgets.items():
            print(f"{month}: {format_money(cents)}")
        return 0
    info = service.budget_show(args.month)
    if info["budget_cents"] is None:
        print(f"No budget set for {info['month']} (spent {format_money(info['spent_cents'])})")
    else:
        left = info["budget_cents"] - info["spent_cents"]
        print(
            f"{info['month']}: spent {format_money(info['spent_cents'])} / "
            f"{format_money(info['budget_cents'])} (remaining {format_money(left)})"
        )
    return 0


def _handle_status(args: argparse.Namespace) -> int:
    # Status never fails the bar: get_status_output degrades to '--' itself.
    print(get_status_output(args.data_file, as_json=args.json, template=args.template))
    return 0


if __name__ == "__main__":  # must stay last: runs after all handlers exist
    console_main()
