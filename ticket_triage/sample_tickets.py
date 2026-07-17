"""sample_tickets.py

Soft-fail JSONL loader for ``ticket_triage/data/sample_tickets.jsonl`` (or
any file of the same per-line-JSON shape).

Design contract:

- Malformed JSON on a line -> SKIP that line, record it with line number
  and reason, continue.
- Valid JSON but ``TicketState.model_validate`` fails -> SKIP that line,
  record it with line number and the schema-error summary, continue.
- Blank lines -> not "malformed"; silently ignored (they represent
  absence of data, not bad data).
- File-level failures (file not found, permission denied, decode error
  on the file itself) -> propagate as their normal exception type.

The loader is deliberately per-line-soft: sample-ticket corpora will
drift over time, one row should not sink an entire batch. Tests that
want strict "every row must parse" behavior can assert
``result.skipped_count == 0`` on the return value.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from ticket_triage.schema import TicketState

_EXCERPT_LEN = 100


@dataclass(slots=True)
class SkippedLine:
    """One line that failed to load, and why."""

    line_number: int
    reason: str
    excerpt: str


@dataclass(slots=True)
class LoadResult:
    """Return value of ``load_sample_tickets``."""

    tickets: list[TicketState] = field(default_factory=list)
    skipped: list[SkippedLine] = field(default_factory=list)

    @property
    def loaded_count(self) -> int:
        """Number of tickets successfully parsed and validated."""
        return len(self.tickets)

    @property
    def skipped_count(self) -> int:
        """Number of lines that failed to load."""
        return len(self.skipped)

    @property
    def total_seen(self) -> int:
        """Total non-blank lines processed (loaded + skipped)."""
        return self.loaded_count + self.skipped_count


def _summarize_validation_error(exc: ValidationError) -> str:
    """Extract a compact first-error summary from a ValidationError.

    Args:
        exc: The Pydantic ValidationError instance.

    Returns:
        A short human-readable string naming the offending field and reason.
        Falls back to ``str(exc)`` if the error list is empty.
    """
    errors = exc.errors()
    if not errors:
        return str(exc)
    first = errors[0]
    loc = ".".join(str(p) for p in first.get("loc", ()))
    msg = first.get("msg", "validation error")
    n = len(errors)
    suffix = f" ({n - 1} more)" if n > 1 else ""
    return f"schema violation at {loc}: {msg}{suffix}"


def load_sample_tickets(path: Path, *, warn: bool = True) -> LoadResult:
    """Load sample tickets from a JSONL file with soft per-line failure.

    Args:
        path: Filesystem path to the JSONL file.
        warn: If True (default), emit a ``UserWarning`` per skipped line so
            callers see the failures in log output. Tests that want silence
            pass ``warn=False``.

    Returns:
        A ``LoadResult`` containing the successfully-parsed tickets and a
        list of ``SkippedLine`` entries describing each failure with its
        1-indexed line number, reason, and a 100-character excerpt of the
        offending source line.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        UnicodeDecodeError: If the file cannot be read as UTF-8.
    """
    result = LoadResult()
    text = path.read_text(encoding="utf-8")

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            reason = f"invalid JSON: {exc.msg} at column {exc.colno}"
            result.skipped.append(
                SkippedLine(
                    line_number=line_number,
                    reason=reason,
                    excerpt=stripped[:_EXCERPT_LEN],
                )
            )
            if warn:
                warnings.warn(
                    f"{path.name}:{line_number} skipped — {reason}",
                    stacklevel=2,
                )
            continue

        try:
            ticket = TicketState.model_validate(data)
        except ValidationError as exc:
            reason = _summarize_validation_error(exc)
            result.skipped.append(
                SkippedLine(
                    line_number=line_number,
                    reason=reason,
                    excerpt=stripped[:_EXCERPT_LEN],
                )
            )
            if warn:
                warnings.warn(
                    f"{path.name}:{line_number} skipped — {reason}",
                    stacklevel=2,
                )
            continue

        result.tickets.append(ticket)

    return result
