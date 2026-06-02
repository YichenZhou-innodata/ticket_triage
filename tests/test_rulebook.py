"""test_rulebook.py

Tests that ``load_rulebook`` parses ``templates/access_request_v1.json`` and
that every state, event, action, and entity-field name in the file is a
valid enum member.
"""

from pathlib import Path

import pytest

from ticket_triage.enums import (
    EntityField,
    Event,
    PrimaryCategory,
    RecommendedActionType,
    State,
)
from ticket_triage.rulebook import Rulebook, RulebookLoadError, load_rulebook


RULEBOOK_PATH = (
    Path(__file__).resolve().parent.parent
    / "ticket_triage"
    / "templates"
    / "access_request_v1.json"
)


@pytest.fixture(scope="module")
def rulebook() -> Rulebook:
    """Load the access_request_v1 rule book once per test module."""
    return load_rulebook(RULEBOOK_PATH)


def test_rulebook_loads(rulebook: Rulebook) -> None:
    """Rule book loads and identifies itself correctly."""
    assert rulebook.name == "access_request_v1"
    assert rulebook.primary_category is PrimaryCategory.ACCESS_REQUEST


def test_required_fields_are_entity_fields(rulebook: Rulebook) -> None:
    """Every required field is a known EntityField enum value."""
    assert rulebook.required_fields, "required_fields must not be empty"
    for field in rulebook.required_fields:
        assert isinstance(field, EntityField)


def test_required_fields_is_only_employee_id(rulebook: Rulebook) -> None:
    """Per the spec, only employee_id is confirmed as required."""
    assert rulebook.required_fields == [EntityField.EMPLOYEE_ID]


def test_provisional_required_fields_are_entity_fields(rulebook: Rulebook) -> None:
    """Provisional required fields parse as valid EntityField enum members."""
    assert rulebook.provisional_required_fields, (
        "provisional list must not be empty for access_request_v1"
    )
    for field in rulebook.provisional_required_fields:
        assert isinstance(field, EntityField)


def test_required_and_provisional_are_disjoint(rulebook: Rulebook) -> None:
    """A field must not appear in both required and provisional lists."""
    overlap = set(rulebook.required_fields) & set(rulebook.provisional_required_fields)
    assert overlap == set(), f"Field(s) in both lists: {overlap}"


def test_required_fields_note_is_populated(rulebook: Rulebook) -> None:
    """The provenance note for required_fields is non-empty."""
    assert rulebook.required_fields_note


def test_allowed_events_per_state_uses_valid_enums(rulebook: Rulebook) -> None:
    """Keys are valid States and values are valid Events."""
    for state, events in rulebook.allowed_events_per_state.items():
        assert isinstance(state, State)
        for event in events:
            assert isinstance(event, Event)


def test_allowed_actions_per_state_uses_valid_enums(rulebook: Rulebook) -> None:
    """Keys are valid States and values are valid RecommendedActionTypes."""
    for state, actions in rulebook.allowed_actions_per_state.items():
        assert isinstance(state, State)
        for action in actions:
            assert isinstance(action, RecommendedActionType)


def test_transitions_use_valid_enums(rulebook: Rulebook) -> None:
    """Every transition references valid States and a valid Event."""
    assert rulebook.transitions, "transitions must not be empty"
    for transition in rulebook.transitions:
        assert isinstance(transition.from_state, State)
        assert isinstance(transition.event, Event)
        assert isinstance(transition.to_state, State)
        assert transition.source in {"spec_explicit", "inferred"}


def test_at_least_one_explicit_transition_from_spec(rulebook: Rulebook) -> None:
    """The ABP-1007 example yields one transition with source=spec_explicit."""
    explicit = [t for t in rulebook.transitions if t.source == "spec_explicit"]
    assert len(explicit) >= 1


def test_unknown_state_raises_clear_error(tmp_path: Path) -> None:
    """An unknown state in the JSON surfaces as a RulebookLoadError."""
    bogus = tmp_path / "bad.json"
    bogus.write_text(
        '{"name": "x", "primary_category": "access_request", '
        '"required_fields": [], '
        '"allowed_events_per_state": {"made_up_state": []}, '
        '"allowed_actions_per_state": {}, "transitions": []}',
        encoding="utf-8",
    )
    with pytest.raises(RulebookLoadError):
        load_rulebook(bogus)
