"""test_schema.py

Tests that ``ticket_triage.schema.TicketState`` parses the ABP-1007 example
from the spec (``access_issue_state_machine.md``).
"""

from ticket_triage.enums import (
    ApprovalStatus,
    EntityField,
    Event,
    PrimaryCategory,
    RecommendedActionType,
    State,
)
from ticket_triage.schema import TicketState


# Copied (near-)literally from access_issue_state_machine.md lines 151-181.
# NOTE: spec inconsistency — line 176 of the .md uses
# `"type": "ask_for_info"` but the canonical Recommended Action Types list at
# line 116 of the .md is `ask_for_missing_info`. Using the canonical enum
# value here. Flag for Yichen review.
ABP_1007: dict = {
    "issue_id": "ABP-1007",
    "rulebook": "access_request_v1",
    "state": "missing_info",
    "primary_category": "access_request",
    "entities": {
        "name": "Taylor Brooks",
        "employee_id": "",
        "portfolio": "Energy Transition",
        "region": "EMEA",
        "user_role": "Viewer",
        "project_type": "pre-planning",
        "leads": ["Priya Nair"],
        "additional_context": "Temporary access for planning readout",
    },
    "missing_fields": ["employee_id"],
    "duplicate_candidates": [],
    "approval": {
        "required": True,
        "approver": "Priya Nair",
        "status": "not_requested",
    },
    "last_event": "missing_required_fields_detected",
    "recommended_action": {
        "type": "ask_for_missing_info",
        "message": "Please provide the user's employee_id so we can process the access request.",
    },
    "confidence": 0.89,
    "requires_human_review": True,
}


def test_abp_1007_parses() -> None:
    """The ABP-1007 example validates as a TicketState."""
    state = TicketState.model_validate(ABP_1007)

    assert state.issue_id == "ABP-1007"
    assert state.rulebook == "access_request_v1"
    assert state.state is State.MISSING_INFO
    assert state.primary_category is PrimaryCategory.ACCESS_REQUEST
    assert state.last_event is Event.MISSING_REQUIRED_FIELDS_DETECTED


def test_abp_1007_entities() -> None:
    """Entity fields from ABP-1007 round-trip correctly."""
    state = TicketState.model_validate(ABP_1007)

    assert state.entities.name == "Taylor Brooks"
    assert state.entities.employee_id == ""
    assert state.entities.portfolio == "Energy Transition"
    assert state.entities.region == "EMEA"
    assert state.entities.user_role == "Viewer"
    assert state.entities.project_type == "pre-planning"
    assert state.entities.leads == ["Priya Nair"]
    assert state.entities.additional_context == "Temporary access for planning readout"


def test_abp_1007_missing_fields_are_enum_values() -> None:
    """``missing_fields`` is parsed as a list of EntityField enum members."""
    state = TicketState.model_validate(ABP_1007)
    assert state.missing_fields == [EntityField.EMPLOYEE_ID]


def test_abp_1007_recommended_action() -> None:
    """Recommended action uses the canonical enum value (see file note)."""
    state = TicketState.model_validate(ABP_1007)
    assert state.recommended_action.type is RecommendedActionType.ASK_FOR_MISSING_INFO
    assert "employee_id" in state.recommended_action.message
    assert state.recommended_action.target is None


def test_abp_1007_approval() -> None:
    """Approval block parses with the inferred ApprovalStatus enum."""
    state = TicketState.model_validate(ABP_1007)
    assert state.approval.required is True
    assert state.approval.approver == "Priya Nair"
    assert state.approval.status is ApprovalStatus.NOT_REQUESTED


def test_abp_1007_top_level_flags() -> None:
    """Top-level scalars from the concrete example."""
    state = TicketState.model_validate(ABP_1007)
    assert state.confidence == 0.89
    assert state.requires_human_review is True


def test_abp_1007_optional_fields_default() -> None:
    """Fields absent from the example default per the reconciliation log."""
    state = TicketState.model_validate(ABP_1007)
    assert state.subcategory is None
    assert state.duplicate_candidates == []
    assert state.audit == []
