# Expense Tracker

A beginner-friendly command-line expense tracker in Python 3.10+ using only the standard library, with a Quickshell status bar widget.

## Install

Requires Python 3.10 or newer. No third-party runtime dependencies.

```bash
cd expense-tracker
pip install -e .
# now the `expense` command is available
expense --help
```

Without installing, you can run it as a module from the project root:

```bash
python -m expense_tracker.cli --help
# (tests use this style so they never touch your real data file)
```

Data lives at `$XDG_DATA_HOME/expense-tracker/expenses.json`
(fallback `~/.local/share/expense-tracker/expenses.json`).
Override per-invocation with `--data-file PATH`.

## Usage

All amounts are positive numbers with at most 2 decimals (`12.50`).
Dates are `YYYY-MM-DD` (default: today). Categories are lowercased.

### add

```bash
expense add 12.50 food -d "lunch"
expense add 4.75 transport --date 2026-03-01
expense add 1200 rent -d "march rent"
```

### list

```bash
expense list
expense list --category food
expense list --from 2026-03-01 --to 2026-03-31
expense list --sort amount
expense list --category food --sort date
```

### delete

```bash
expense delete 3
```

Deleted IDs are recycled: a new entry takes the smallest free ID.

### edit

```bash
expense edit 1 --amount 15.00
expense edit 2 --category groceries --description "weekly shop"
expense edit 1 --date 2026-03-02
```

### summary

```bash
expense summary
expense summary --month 2026-03
expense summary --by category
expense summary --month 2026-03 --by category
```

### details

Month overview for humans and widgets: hero total, budget state,
per-category breakdown, and recent expenses.

```bash
expense details
expense details --month 2026-03
expense details --json
```

### export

```bash
expense export /tmp/expenses.csv
expense export /tmp/expenses.json --format json
```

Format defaults from the file extension (`.json` → json, otherwise csv).

### budget

```bash
expense budget set 500
expense budget set 600 --month 2026-04
expense budget show
expense budget show --month 2026-04
expense budget show --all
```

### status (for the status bar)

```bash
expense status
expense status --json
expense status --format "{month_total} spent ({percent}%)"
```

Plain output is one line (`₱342.50 / ₱500.00`, or `₱342.50` with no budget).
`--json` emits `text, tooltip, month_total, budget, percent, state, currency`.
Template placeholders: `text, tooltip, month_total, budget, percent, state, currency`.
Missing or unreadable data degrades to `--` (plain) or a zeroed JSON object, always exit 0.

### Global flags

```bash
expense --data-file /tmp/demo.json list
expense --version
expense --help
expense add --help
```

## Exit codes and errors

- `0` success
- `1` runtime/storage error (e.g. corrupted data file)
- `2` usage/validation error (bad amount, date, category, unknown ID)

Errors are one line on stderr, never a traceback. If the JSON file is
corrupted, it is copied to `expenses.json.bak` (original left untouched)
and the command exits 1 — except `status`, which degrades to `--` / zeroed
JSON with exit 0 so the bar never breaks.

## Running tests

```bash
python -m unittest discover tests
```

Tests use temporary directories only and never touch your real data file.

## Quickshell setup

`quickshell/ExpenseStatus.qml` is a self-contained widget. It runs
`expense status --json` via `Quickshell.Io` `Process` + `StdioCollector`,
refreshes every 60 s and on click, colors text by `state`
(green / yellow / red), and shows the breakdown as a hover tooltip.

Minimal embedding in your Quickshell `shell.qml` bar:

```qml
import QtQuick
import QtQuick.Layouts
import Quickshell

ShellRoot {
    Variants {
        model: Quickshell.screens
        PanelWindow {
            required property var modelData
            screen: modelData
            anchors { top: true; left: true; right: true }
            height: 30
            RowLayout {
                anchors.fill: parent
                // ... your other widgets ...
                ExpenseStatus {}  // ensure quickshell/ dir is on your QML import path
            }
        }
    }
}
```

Make sure `expense` is on the PATH Quickshell sees (e.g. `pip install -e .`
into the same environment, or symlink the binary into `~/.local/bin`).

> API note: written against the documented `Quickshell.Io` `Process` /
> `StdioCollector` pattern (Quickshell 0.x). If your Quickshell release
> renamed those properties, consult the Io module docs for your version —
> the JSON schema and Timer/parse logic are plain QtQuick and carry over.
