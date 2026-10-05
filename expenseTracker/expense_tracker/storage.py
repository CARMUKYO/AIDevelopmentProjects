"""JSON file persistence with atomic writes and corruption backup.

File layout: {"schema_version": 1, "next_id": int,
              "expenses": [...], "budgets": {"YYYY-MM": cents}}.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .errors import StorageError, ValidationError
from .models import Expense, parse_month

SCHEMA_VERSION = 1


@dataclass
class StoreData:
    """In-memory snapshot of the JSON file."""

    expenses: list[Expense] = field(default_factory=list)
    next_id: int = 1
    budgets: dict[str, int] = field(default_factory=dict)


def get_default_data_file() -> Path:
    """Resolve $XDG_DATA_HOME/expense-tracker/expenses.json with fallback."""
    xdg = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".local" / "share"
    return base / "expense-tracker" / "expenses.json"


def resolve_data_file(override: str | Path | None) -> Path:
    """Return the override path, or the default data file location."""
    if override is not None:
        return Path(override).expanduser()
    return get_default_data_file()


def _backup_corrupted(path: Path) -> Path:
    """Copy a corrupted file to '<name>.bak' without removing the original."""
    backup = path.with_name(path.name + ".bak")
    shutil.copy2(path, backup)
    return backup


def load_data(
    data_file: str | Path | None = None, backup: bool = True
) -> tuple[Path, StoreData]:
    """Load the store. Missing file yields an empty store (no write).

    Set backup=False for read-only callers (status bar) that must never write.
    """
    path = resolve_data_file(data_file)
    if not path.exists():
        return path, StoreData()
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        if backup:
            backup_path = _try_backup(path)
            raise StorageError(
                f"data file is corrupted ({exc}); backup saved to {backup_path}"
            ) from None
        raise StorageError(f"data file is corrupted ({exc})") from None
    try:
        store = _parse_payload(payload)
    except ValidationError as exc:
        if backup:
            backup_path = _try_backup(path)
            raise StorageError(
                f"data file is corrupted ({exc}); backup saved to {backup_path}"
            ) from None
        raise StorageError(f"data file is corrupted ({exc})") from None
    return path, store


def _try_backup(path: Path) -> Path:
    """Best-effort backup; never let the backup itself hide the root cause."""
    try:
        return _backup_corrupted(path)
    except OSError:
        return path.with_name(path.name + ".bak")


def _parse_payload(payload: object) -> StoreData:
    """Validate the top-level JSON structure."""
    if not isinstance(payload, dict):
        raise ValidationError("top-level JSON must be an object")
    version = payload.get("schema_version", 1)
    if version != SCHEMA_VERSION:
        raise ValidationError(f"unsupported schema_version: {version!r}")
    next_id = payload.get("next_id", 1)
    if not isinstance(next_id, int) or next_id <= 0:
        raise ValidationError("next_id must be a positive integer")
    raw_expenses = payload.get("expenses", [])
    if not isinstance(raw_expenses, list):
        raise ValidationError("expenses must be a list")
    expenses = [Expense.from_dict(item) for item in raw_expenses]
    raw_budgets = payload.get("budgets", {})
    if not isinstance(raw_budgets, dict):
        raise ValidationError("budgets must be an object")
    budgets: dict[str, int] = {}
    for month, cents in raw_budgets.items():
        month = parse_month(str(month))
        if not isinstance(cents, int) or cents <= 0:
            raise ValidationError(f"invalid budget for {month}")
        budgets[month] = cents
    return StoreData(expenses=expenses, next_id=next_id, budgets=budgets)


def save_data(path: str | Path, store: StoreData) -> None:
    """Persist the store atomically (temp file + os.replace)."""
    dest = Path(path).expanduser()
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "next_id": store.next_id,
            "expenses": [e.to_dict() for e in store.expenses],
            "budgets": dict(store.budgets),
        }
        # Same directory so os.replace stays on one filesystem (atomic).
        fd, tmp_name = tempfile.mkstemp(
            dir=str(dest.parent), prefix=dest.name + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, dest)
        except BaseException:
            _silent_unlink(tmp_name)
            raise
    except StorageError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise StorageError(f"could not save data file {dest}: {exc}") from None


def _silent_unlink(tmp_name: str) -> None:
    """Remove a leftover temp file; failures here must not mask the real error."""
    try:
        os.unlink(tmp_name)
    except OSError:
        pass
