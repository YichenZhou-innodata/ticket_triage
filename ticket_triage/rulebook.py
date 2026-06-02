"""rulebook.py

Load and validate JSON rule books that drive the triage state machine.

A rule book is the machine-readable counterpart of the markdown spec
(see [ADR 0001](../docs/decisions/0001-rulebook-format.md)). Loading goes
through Pydantic, which validates that every state, event, action, and
entity-field name in the JSON is a member of the corresponding enum in
`ticket_triage.enums`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ticket_triage.enums import (
    EntityField,
    Event,
    PrimaryCategory,
    RecommendedActionType,
    State,
)


class Transition(BaseModel):
    """One (from_state, event) -> to_state edge in the state machine."""

    model_config = ConfigDict(extra="forbid")

    from_state: State = Field(..., description="State before the transition.")
    event: Event = Field(..., description="Event that triggers the transition.")
    to_state: State = Field(..., description="State after the transition.")
    source: str = Field(
        ...,
        description="Provenance of the transition: 'spec_explicit' or 'inferred'.",
    )
    evidence: str | None = Field(
        default=None,
        description="Short justification for the transition.",
    )


class Rulebook(BaseModel):
    """A validated rule book for one primary category."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(..., description="Rule-book identifier, e.g. 'access_request_v1'.")
    primary_category: PrimaryCategory = Field(
        ..., description="Primary ticket category this rule book applies to."
    )
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Human-readable provenance / TODO notes per section.",
    )
    required_fields: list[EntityField] = Field(
        ...,
        description="Entity fields that the spec confirms must be populated to advance the ticket.",
    )
    provisional_required_fields: list[EntityField] = Field(
        default_factory=list,
        description=(
            "Entity fields inferred as required from the spec's Entity Schema "
            "but not yet confirmed by the spec author. Move into required_fields "
            "once confirmed."
        ),
    )
    required_fields_note: str = Field(
        default="",
        alias="_required_fields_note",
        description="Provenance note explaining the split between required and provisional required fields.",
    )
    allowed_events_per_state: dict[State, list[Event]] = Field(
        ...,
        description="For each state, the set of events that are valid inputs.",
    )
    allowed_actions_per_state: dict[State, list[RecommendedActionType]] = Field(
        ...,
        description="For each state, the set of action types the agent may recommend.",
    )
    transitions: list[Transition] = Field(
        ..., description="Enumerated state-machine transitions."
    )
    todo_transitions: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Transitions the spec is too ambiguous to commit to. Free-form "
            "shape; intended for human review, not for the runtime."
        ),
    )


class RulebookLoadError(ValueError):
    """Raised when a rule book file cannot be read or validated."""


def load_rulebook(path: Path) -> Rulebook:
    """Load and validate a rule book JSON file.

    Args:
        path: Filesystem path to the rule book JSON file.

    Returns:
        A validated ``Rulebook`` instance.

    Raises:
        RulebookLoadError: If the file is missing, not valid JSON, or does
            not conform to the ``Rulebook`` schema (including references to
            unknown enum values for states, events, actions, or fields).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RulebookLoadError(f"Rule book not found at {path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RulebookLoadError(f"Rule book at {path} is not valid JSON: {exc}") from exc

    try:
        return Rulebook.model_validate(data)
    except ValidationError as exc:
        raise RulebookLoadError(
            f"Rule book at {path} failed schema validation:\n{exc}"
        ) from exc
