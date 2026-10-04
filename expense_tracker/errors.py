"""Custom exceptions for the expense tracker.

Why a separate module: callers (CLI, service, storage) need to agree on
failure types without importing each other. The CLI maps each type to a
distinct exit code, so keep the hierarchy stable.
"""

from __future__ import annotations


class ExpenseTrackerError(Exception):
    """Base class for all expected expense-tracker failures."""


class ValidationError(ExpenseTrackerError):
    """User supplied bad input. CLI exit code 2."""


class ExpenseNotFoundError(ValidationError):
    """An expense ID does not exist. Still a usage error, so exit code 2."""


class StorageError(ExpenseTrackerError):
    """Data file is missing, unreadable, or corrupted. CLI exit code 1."""
