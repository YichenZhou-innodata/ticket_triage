"""test_validation.py

Adversarial tests for the schema, rule book, and JSONL loader.

Verifies:

- Schema field-level constraints (non-empty, max length, strict types,
  enum membership, extra="forbid") reject bad input with actionable
  messages.
- Rule-book validation catches unknown enum values, missing required
  keys, malformed JSON, and transitions that reference states the rule
  book does not otherwise declare.
- The soft-fail JSONL loader skips bad lines, keeps loading the rest,
  reports what was skipped, and emits warnings by default.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

from ticket_triage.rulebook import RulebookLoadError, load_rulebook
from ticket_triage.sample_tickets import load_sample_tickets
from ticket_triage.schema import TicketState


MINIMAL_TICKET: dict = {
    "issue_id": "X-1",
    "rulebook": "access_request_v1",
    "state": "intake",
    "primary_category": "access_request",
    "entities": {},
    "approval": {"required": False, "status": "not_requested"},
    "last_event": "ticket_created",
    "recommended_action": {"type": "extract_fields", "message": "ok"},
    "confidence": 0.5,
    "requires_human_review": True,
}


# ============================================================================
# SCHEMA — the minimal ticket must still parse
# ============================================================================


def test_minimal_ticket_parses() -> None:
    """Baseline: with everything valid, the minimal ticket loads."""
    ticket = TicketState.model_validate(MINIMAL_TICKET)
    assert ticket.issue_id == "X-1"


# ============================================================================
# SCHEMA — required non-empty strings
# ============================================================================


def test_empty_issue_id_rejected() -> None:
    """An empty issue_id must be rejected and the error must name the field."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "issue_id": ""})
    msg = str(exc_info.value)
    assert "issue_id" in msg


def test_empty_rulebook_field_rejected() -> None:
    """An empty rulebook identifier must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "rulebook": ""})
    assert "rulebook" in str(exc_info.value)


def test_empty_recommended_action_message_rejected() -> None:
    """Recommended action must have a non-empty message."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate(
            {
                **MINIMAL_TICKET,
                "recommended_action": {"type": "extract_fields", "message": ""},
            }
        )
    assert "message" in str(exc_info.value)


# ============================================================================
# SCHEMA — oversized strings and lists
# ============================================================================


def test_oversized_issue_id_rejected() -> None:
    """A pathologically long issue_id must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "issue_id": "X" * 100_000})
    assert "issue_id" in str(exc_info.value)


def test_oversized_additional_context_rejected() -> None:
    """A pathologically long additional_context must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate(
            {
                **MINIMAL_TICKET,
                "entities": {"additional_context": "X" * 1_000_000},
            }
        )
    msg = str(exc_info.value)
    assert "additional_context" in msg


def test_oversized_missing_fields_list_rejected() -> None:
    """An unbounded missing_fields list is rejected at the schema boundary."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate(
            {**MINIMAL_TICKET, "missing_fields": ["employee_id"] * 100}
        )
    assert "missing_fields" in str(exc_info.value)


# ============================================================================
# SCHEMA — strict types and enum membership
# ============================================================================


def test_wrong_type_for_confidence_rejected() -> None:
    """A string where a float is expected must be rejected (no silent coercion)."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "confidence": "0.5"})
    assert "confidence" in str(exc_info.value)


def test_confidence_out_of_range_rejected() -> None:
    """Confidence above 1.0 must be rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "confidence": 1.5})
    assert "confidence" in str(exc_info.value)


def test_unknown_state_value_rejected_with_value_in_message() -> None:
    """Unknown state enum value: error must name the field and the offending value."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "state": "totally_made_up"})
    msg = str(exc_info.value)
    assert "state" in msg
    assert "totally_made_up" in msg


def test_extra_top_level_key_rejected() -> None:
    """extra='forbid' rejects unknown top-level keys."""
    with pytest.raises(ValidationError) as exc_info:
        TicketState.model_validate({**MINIMAL_TICKET, "surprise": "boom"})
    assert "surprise" in str(exc_info.value)


def test_int_for_bool_rejected_under_strict() -> None:
    """Strict mode: 1 or 0 are NOT accepted where a bool is expected."""
    with pytest.raises(ValidationError):
        TicketState.model_validate({**MINIMAL_TICKET, "requires_human_review": 1})


# ============================================================================
# RULE BOOK — file-level failure modes fail loud
# ============================================================================


def _write_json(tmp_path: Path, name: str, payload: dict) -> Path:
    """Write a dict as JSON into tmp_path and return the resulting path."""
    file_path = tmp_path / name
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    return file_path


def test_missing_rulebook_file_raises_clear_error(tmp_path: Path) -> None:
    """A missing file surfaces as RulebookLoadError with the path in the message."""
    ghost = tmp_path / "does_not_exist.json"
    with pytest.raises(RulebookLoadError) as exc_info:
        load_rulebook(ghost)
    assert "not found" in str(exc_info.value).lower()


def test_malformed_rulebook_json_raises_clear_error_with_location(tmp_path: Path) -> None:
    """Non-parseable JSON reports the parse position and file."""
    bad = tmp_path / "bad.json"
    bad.write_text("{ this is: not valid json ]", encoding="utf-8")
    with pytest.raises(RulebookLoadError) as exc_info:
        load_rulebook(bad)
    msg = str(exc_info.value)
    assert "not valid JSON" in msg
    assert "line" in msg
    assert "column" in msg


def test_rulebook_missing_required_key_raises(tmp_path: Path) -> None:
    """Missing top-level required keys are named in the error."""
    path = _write_json(tmp_path, "empty.json", {"name": "x"})
    with pytest.raises(RulebookLoadError) as exc_info:
        load_rulebook(path)
    msg = str(exc_info.value).lower()
    assert "required" in msg or "missing" in msg or "field" in msg


def test_rulebook_unknown_enum_value_raises_clear_error(tmp_path: Path) -> None:
    """Unknown state key in allowed_events_per_state is flagged with the value."""
    bogus = {
        "name": "x",
        "primary_category": "access_request",
        "required_fields": [],
        "allowed_events_per_state": {"totally_fake_state": []},
        "allowed_actions_per_state": {},
        "transitions": [],
    }
    path = _write_json(tmp_path, "unknown_state.json", bogus)
    with pytest.raises(RulebookLoadError) as exc_info:
        load_rulebook(path)
    assert "totally_fake_state" in str(exc_info.value)


def test_rulebook_transition_from_undeclared_state_raises(tmp_path: Path) -> None:
    """A transition whose from_state is not in allowed_events_per_state raises."""
    bogus = {
        "name": "x",
        "primary_category": "access_request",
        "required_fields": [],
        "allowed_events_per_state": {"intake": []},
        "allowed_actions_per_state": {},
        "transitions": [
            {
                "from_state": "verification",
                "event": "user_confirmed_access",
                "to_state": "resolved",
                "source": "spec_explicit",
            }
        ],
    }
    path = _write_json(tmp_path, "inconsistent.json", bogus)
    with pytest.raises(RulebookLoadError) as exc_info:
        load_rulebook(path)
    msg = str(exc_info.value)
    assert "verification" in msg
    assert "undeclared" in msg.lower() or "does not appear" in msg


# ============================================================================
# JSONL LOADER — soft-fail per line
# ============================================================================


def _write_lines(tmp_path: Path, name: str, lines: list[str]) -> Path:
    """Write a list of lines as a JSONL file."""
    file_path = tmp_path / name
    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_path


def _minimal_ticket_line() -> str:
    """Return a JSON-encoded minimal ticket suitable for a JSONL line."""
    return json.dumps(MINIMAL_TICKET)


def test_jsonl_loader_all_valid_loads_everything(tmp_path: Path) -> None:
    """A clean file loads all tickets with zero skipped and no warnings."""
    path = _write_lines(
        tmp_path,
        "clean.jsonl",
        [_minimal_ticket_line(), _minimal_ticket_line()],
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        result = load_sample_tickets(path, warn=False)
    assert result.loaded_count == 2
    assert result.skipped_count == 0
    assert result.total_seen == 2


def test_jsonl_loader_malformed_line_skipped_rest_load(tmp_path: Path) -> None:
    """A malformed JSON line is skipped; valid lines around it still load."""
    path = _write_lines(
        tmp_path,
        "one_bad.jsonl",
        [
            _minimal_ticket_line(),
            "{ this is not valid json",
            _minimal_ticket_line(),
        ],
    )
    result = load_sample_tickets(path, warn=False)
    assert result.loaded_count == 2
    assert result.skipped_count == 1
    assert result.skipped[0].line_number == 2
    assert "JSON" in result.skipped[0].reason or "json" in result.skipped[0].reason


def test_jsonl_loader_schema_invalid_line_skipped_rest_load(tmp_path: Path) -> None:
    """A valid-JSON line that fails schema is skipped with a schema reason."""
    path = _write_lines(
        tmp_path,
        "bad_schema.jsonl",
        [
            _minimal_ticket_line(),
            json.dumps({**MINIMAL_TICKET, "state": "not_a_real_state"}),
            _minimal_ticket_line(),
        ],
    )
    result = load_sample_tickets(path, warn=False)
    assert result.loaded_count == 2
    assert result.skipped_count == 1
    assert result.skipped[0].line_number == 2
    assert "state" in result.skipped[0].reason


def test_jsonl_loader_blank_lines_ignored_not_reported_as_skipped(tmp_path: Path) -> None:
    """Blank lines are not 'malformed'; they are silently ignored."""
    path = _write_lines(
        tmp_path,
        "blanks.jsonl",
        [
            _minimal_ticket_line(),
            "",
            _minimal_ticket_line(),
            "   ",
            _minimal_ticket_line(),
        ],
    )
    result = load_sample_tickets(path, warn=False)
    assert result.loaded_count == 3
    assert result.skipped_count == 0


def test_jsonl_loader_emits_warning_per_skipped_line_by_default(tmp_path: Path) -> None:
    """With warn=True (default), each skipped line emits a Python warning."""
    path = _write_lines(
        tmp_path,
        "warn.jsonl",
        [
            _minimal_ticket_line(),
            "{ not json",
            json.dumps({**MINIMAL_TICKET, "confidence": 2.0}),
        ],
    )
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        result = load_sample_tickets(path, warn=True)
    assert result.loaded_count == 1
    assert result.skipped_count == 2
    assert len(recorded) == 2
    for w in recorded:
        assert "skipped" in str(w.message).lower()


def test_jsonl_loader_reports_line_numbers_and_excerpts(tmp_path: Path) -> None:
    """Skipped lines carry their 1-indexed line number and a text excerpt."""
    path = _write_lines(
        tmp_path,
        "excerpts.jsonl",
        [
            _minimal_ticket_line(),
            "totally garbage here",
        ],
    )
    result = load_sample_tickets(path, warn=False)
    assert result.skipped_count == 1
    skipped = result.skipped[0]
    assert skipped.line_number == 2
    assert "totally garbage here" in skipped.excerpt
