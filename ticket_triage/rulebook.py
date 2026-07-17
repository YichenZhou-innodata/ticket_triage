"""rulebook.py

Load and validate JSON rule books that drive the triage state machine.

A rule book is the machine-readable counterpart of the markdown spec
(see [ADR 0001](../docs/decisions/0001-rulebook-format.md)). Loading goes
through Pydantic, which validates that every state, event, action, and
entity-field name in the JSON is a member of the corresponding enum in
`ticket_triage.enums`.

Validation policy (audit-driven):

- All models use ``extra="forbid"`` — unknown JSON keys are rejected.
- A model-level validator checks that every transition's ``from_state``
  appears as a key in ``allowed_events_per_state`` — this catches rule
  books whose transition graph references states the rule book itself
  does not otherwise declare.
- ``load_rulebook`` wraps every failure mode in ``RulebookLoadError``
  with file path and (where available) line/column information so
  malformed rule books fail LOUD and CLEAR.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

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
        min_length=1,
        max_length=64,
        description="Provenance of the transition: 'spec_explicit' or 'inferred'.",
    )
    evidence: str | None = Field(
        default=None,
        max_length=10_000,
        description="Short justification for the transition.",
    )


class Rulebook(BaseModel):
    """A validated rule book for one primary category."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Rule-book identifier, e.g. 'access_request_v1'.",
    )
    primary_category: PrimaryCategory = Field(
        ..., description="Primary ticket category this rule book applies to."
    )
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Human-readable provenance / TODO notes per section.",
    )
    required_fields: list[EntityField] = Field(
        ...,
        max_length=64,
        description=(
            "Entity fields that the spec confirms must be populated to advance "
            "the ticket."
        ),
    )
    provisional_required_fields: list[EntityField] = Field(
        default_factory=list,
        max_length=64,
        description=(
            "Entity fields inferred as required from the spec's Entity Schema "
            "but not yet confirmed by the spec author. Move into "
            "required_fields once confirmed."
        ),
    )
    required_fields_note: str = Field(
        default="",
        max_length=10_000,
        alias="_required_fields_note",
        description=(
            "Provenance note explaining the split between required and "
            "provisional required fields."
        ),
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
        ...,
        max_length=1000,
        description="Enumerated state-machine transitions.",
    )
    todo_transitions: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=1000,
        description=(
            "Transitions the spec is too ambiguous to commit to. Free-form "
            "shape; intended for human review, not for the runtime."
        ),
    )

    @model_validator(mode="after")
    def _check_transition_consistency(self) -> "Rulebook":
        """Every transition's ``from_state`` must appear in ``allowed_events_per_state``.

        The rule book is inconsistent if it declares a transition from a state
        it never lists in its own state map. This validator flags that as a
        loud error rather than a silent trap for downstream code.
        """
        allowed_states = set(self.allowed_events_per_state.keys())
        problems: list[str] = []
        for i, transition in enumerate(self.transitions):
            if transition.from_state not in allowed_states:
                problems.append(
                    f"transitions[{i}]: from_state '{transition.from_state.value}' "
                    f"does not appear as a key in allowed_events_per_state"
                )
        if problems:
            raise ValueError(
                "Rule book transitions reference undeclared states:\n  - "
                + "\n  - ".join(problems)
            )
        return self


class RulebookLoadError(ValueError):
    """Raised when a rule book file cannot be read or validated."""


def load_rulebook(path: Path) -> Rulebook:
    """Load and validate a rule book JSON file.

    Fails LOUD and CLEAR on every error path — malformed JSON, missing
    required keys, unknown enum values, and inconsistent transitions all
    surface as ``RulebookLoadError`` with the file path and, where the
    underlying error provides it, the offending line and column.

    Args:
        path: Filesystem path to the rule book JSON file.

    Returns:
        A validated ``Rulebook`` instance.

    Raises:
        RulebookLoadError: If the file is missing, not valid JSON, or does
            not conform to the ``Rulebook`` schema (including references to
            unknown enum values for states, events, actions, or fields, and
            transitions that reference undeclared states).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RulebookLoadError(f"Rule book not found at {path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RulebookLoadError(
            f"Rule book at {path} is not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}: {exc.msg}"
        ) from exc

    try:
        return Rulebook.model_validate(data)
    except ValidationError as exc:
        raise RulebookLoadError(
            f"Rule book at {path} failed schema validation:\n{exc}"
        ) from exc
