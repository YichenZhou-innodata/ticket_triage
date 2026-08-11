"""test_recommendation.py

Tests `ticket_triage.domain.recommendation.get_next_action` against every
sample ticket in `ticket_triage/data/sample_tickets.jsonl`.

Structure:
    - 4 scenarios pass under the current rule cascade (missing-fields and
      duplicate branches work correctly).
    - 6 scenarios are marked `@pytest.mark.xfail` with reasons describing
      specific gaps in the cascade. Each xfail flips to XPASS automatically
      when the cascade is made state-aware — collectively they are the
      acceptance criteria for the recommendation follow-up: all 6 xfails
      passing = 10/10 coverage.

Root-cause groupings for the xfails:
    - Group A: missing state branches (001, 006, 007)
    - Group B: content-before-state ordering bug (008, 010)
    - Group C: cannot distinguish fresh vs reopened intake (009)
"""

import json
from pathlib import Path

import pytest

from ticket_triage.domain.recommendation import get_next_action
from ticket_triage.enums import (
    ApprovalStatus,
    EntityField,
    Event,
    PrimaryCategory,
    RecommendedActionType,
    State,
)
from ticket_triage.schema import (
    Approval,
    DuplicateCandidate,
    Entities,
    RecommendedAction,
    TicketState,
)


SAMPLE_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "ticket_triage"
    / "data"
    / "sample_tickets.jsonl"
)


@pytest.fixture(scope="module")
def tickets_by_id() -> dict[str, TicketState]:
    """Load all sample tickets once and index by issue_id."""
    lines = SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    tickets = [
        TicketState.model_validate(json.loads(line)) for line in lines if line.strip()
    ]
    return {t.issue_id: t for t in tickets}


def _assert_recommendation(
    tickets_by_id: dict[str, TicketState],
    issue_id: str,
    expected: RecommendedActionType,
) -> None:
    """Look up a ticket, run the recommendation, assert the expected type."""
    ticket = tickets_by_id[issue_id]
    result = get_next_action(ticket)
    assert result.type is expected, (
        f"{issue_id} in state {ticket.state.value}: "
        f"expected {expected.value}, got {result.type.value}"
    )


# ----------------------------------------------------------------------------
# Currently passing (4)
#
# The cascade's first two branches correctly handle these cases:
#     if missing_fields:            -> ask_for_missing_info
#     elif duplicate_candidates:    -> suggest_duplicate_review
# ----------------------------------------------------------------------------


def test_sample_002_missing_employee_id(tickets_by_id: dict[str, TicketState]) -> None:
    """Only employee_id missing -> ask_for_missing_info."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-002", RecommendedActionType.ASK_FOR_MISSING_INFO
    )


def test_sample_003_missing_name_and_employee_id(
    tickets_by_id: dict[str, TicketState],
) -> None:
    """Name and employee_id both missing -> ask_for_missing_info."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-003", RecommendedActionType.ASK_FOR_MISSING_INFO
    )


def test_sample_004_duplicate_review(tickets_by_id: dict[str, TicketState]) -> None:
    """Duplicate candidates populated -> suggest_duplicate_review."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-004", RecommendedActionType.SUGGEST_DUPLICATE_REVIEW
    )


def test_sample_005_missing_leads(tickets_by_id: dict[str, TicketState]) -> None:
    """Leads missing -> ask_for_missing_info (no approver identified)."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-005", RecommendedActionType.ASK_FOR_MISSING_INFO
    )


# ----------------------------------------------------------------------------
# Group A: missing state branches (001, 006, 007)
#
# The cascade only has one state check (`state == INTAKE`). Every other state
# falls through to escalate_to_human. Fix: add state-aware branches for
# ready_for_access_review, access_provisioning, denied — ideally driven by
# access_request_v1.json's allowed_actions_per_state map.
# ----------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "state-blind cascade: no branch for ready_for_access_review; "
        "falls through to escalate_to_human"
    )
)
def test_sample_001_ready_for_access_review(
    tickets_by_id: dict[str, TicketState],
) -> None:
    """Ready-for-review, no missing fields, no duplicates -> request_approval."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-001", RecommendedActionType.REQUEST_APPROVAL
    )


@pytest.mark.xfail(
    reason=(
        "state-blind cascade: no branch for access_provisioning; "
        "falls through to escalate_to_human"
    )
)
def test_sample_006_access_provisioning(tickets_by_id: dict[str, TicketState]) -> None:
    """Approval granted, provisioning stage -> recommend_route_to_access_admin."""
    _assert_recommendation(
        tickets_by_id,
        "SAMPLE-006",
        RecommendedActionType.RECOMMEND_ROUTE_TO_ACCESS_ADMIN,
    )


@pytest.mark.xfail(
    reason=(
        "state-blind cascade: no branch for denied; "
        "falls through to escalate_to_human"
    )
)
def test_sample_007_denied(tickets_by_id: dict[str, TicketState]) -> None:
    """Approval denied -> draft_denial_comment."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-007", RecommendedActionType.DRAFT_DENIAL_COMMENT
    )


# ----------------------------------------------------------------------------
# Group B: ordering bug — content checked before state (008, 010)
#
# The cascade checks missing_fields FIRST, before considering the current
# state. Tickets that have missing_fields set from an earlier state but have
# since advanced to stale_waiting_for_user or human_review get the wrong
# recommendation. Fix: check current state first (or consult the rulebook's
# allowed_actions_per_state) before falling back to the content-based rules.
# ----------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "ordering bug: missing_fields checked before state, so "
        "stale_waiting_for_user with lingering missing_fields returns "
        "ask_for_missing_info instead of send_follow_up_reminder"
    )
)
def test_sample_008_stale_waiting_for_user(
    tickets_by_id: dict[str, TicketState],
) -> None:
    """Stale ticket -> send_follow_up_reminder, not re-ask for the same info."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-008", RecommendedActionType.SEND_FOLLOW_UP_REMINDER
    )


@pytest.mark.xfail(
    reason=(
        "ordering bug: missing_fields checked before state, so human_review "
        "with missing entities returns ask_for_missing_info instead of "
        "escalate_to_human"
    )
)
def test_sample_010_human_review(tickets_by_id: dict[str, TicketState]) -> None:
    """Ticket already in human_review -> escalate_to_human (stay put)."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-010", RecommendedActionType.ESCALATE_TO_HUMAN
    )


# ----------------------------------------------------------------------------
# Group C: cannot distinguish fresh vs reopened intake (009)
#
# The cascade's `state == INTAKE` branch always returns request_approval. A
# reopened ticket is also in state=intake but needs extract_fields to re-run
# the pipeline. Fix: check last_event (ticket_reopened) or audit history to
# distinguish the two.
# ----------------------------------------------------------------------------


@pytest.mark.xfail(
    reason=(
        "cascade cannot distinguish fresh intake from reopened intake; "
        "returns request_approval instead of extract_fields for reopened tickets"
    )
)
def test_sample_009_reopened_intake(tickets_by_id: dict[str, TicketState]) -> None:
    """Reopened intake -> extract_fields (re-run extraction, not approval)."""
    _assert_recommendation(
        tickets_by_id, "SAMPLE-009", RecommendedActionType.EXTRACT_FIELDS
    )


# ----------------------------------------------------------------------------
# OTHER-category guard (item 1.2)
#
# Defense-in-depth backstop for when the model constructs a TicketState with
# primary_category=OTHER and calls get_next_action anyway (ignoring the
# instruction to call escalate_unsupported_ticket instead). The guard at the
# top of get_next_action must fire an early-return escalation regardless of
# state, missing_fields, or duplicate_candidates. It must also preserve the
# requires_human_review invariant and the audit-trail invariant.
#
# RESIDUAL FAILURE MODE — READ THIS BEFORE ASSUMING THE GUARD IS COMPLETE.
#
# The guard fires on the TicketState's primary_category field. It relies on
# the model faithfully propagating classify_ticket's return value into the
# TicketState it constructs when calling get_next_action.
#
# If the model IGNORES classify_ticket's OTHER return and constructs a
# TicketState with primary_category=ACCESS_REQUEST anyway (deciding on its
# own that the ticket "looks like" an access request), the guard does NOT
# fire — the cascade runs, and the pipeline may again ask a bug reporter
# for their employee_id. That is the exact original bug 1.1/1.2 fix,
# surviving as a compliance-dependent failure mode.
#
# This is an LLM-behavior concern, not something these unit tests can
# exercise. The mitigations that exist today are the instruction updates
# in agent.py (item 1.2 — telling the model explicitly what to do on OTHER)
# and the fact that classify_ticket runs as a tool call, so its return
# lands in the conversation as visible signal rather than being hidden.
# A stronger fix (compelling propagation) would need instruction-quality
# work; noted here so this residual failure mode is not forgotten.
# ----------------------------------------------------------------------------


def _minimal_ticket_state_with_category(
    category: PrimaryCategory, **overrides
) -> TicketState:
    """Build a minimal TicketState with the given primary_category.

    Extensible via ``**overrides`` so each guard test can vary the specific
    field(s) it's exercising (state, missing_fields, duplicate_candidates)
    without duplicating the whole state construction.
    """
    defaults: dict = {
        "issue_id": "TEST-OTHER",
        "rulebook": "access_request_v1",
        "state": State.INTAKE,
        "primary_category": category,
        "entities": Entities(),
        "approval": Approval(required=False, status=ApprovalStatus.NOT_REQUESTED),
        "last_event": Event.TICKET_CREATED,
        "recommended_action": RecommendedAction(
            type=RecommendedActionType.EXTRACT_FIELDS,
            message="placeholder",
        ),
        "confidence": 0.5,
        "requires_human_review": False,
    }
    defaults.update(overrides)
    return TicketState.model_validate(defaults)


def test_other_category_returns_escalation() -> None:
    """primary_category=OTHER short-circuits to ESCALATE_TO_HUMAN."""
    ticket_state = _minimal_ticket_state_with_category(PrimaryCategory.OTHER)
    result = get_next_action(ticket_state)
    assert result.type is RecommendedActionType.ESCALATE_TO_HUMAN


def test_other_category_ignores_missing_fields() -> None:
    """The guard fires before the missing_fields branch of the cascade.

    Without the guard, missing_fields would trigger ASK_FOR_MISSING_INFO
    — the exact bug items 1.1/1.2 fix (asking a bug reporter for an
    employee_id).
    """
    ticket_state = _minimal_ticket_state_with_category(
        PrimaryCategory.OTHER,
        missing_fields=[EntityField.EMPLOYEE_ID, EntityField.NAME],
    )
    result = get_next_action(ticket_state)
    assert result.type is RecommendedActionType.ESCALATE_TO_HUMAN


def test_other_category_ignores_duplicate_candidates() -> None:
    """The guard fires before the duplicate_candidates branch of the cascade."""
    ticket_state = _minimal_ticket_state_with_category(
        PrimaryCategory.OTHER,
        duplicate_candidates=[DuplicateCandidate(issue_id="DUP-1")],
    )
    result = get_next_action(ticket_state)
    assert result.type is RecommendedActionType.ESCALATE_TO_HUMAN


@pytest.mark.parametrize(
    "state",
    [
        # Cascade has an explicit branch for INTAKE — guard must still win.
        State.INTAKE,
        # Cascade's missing_fields branch would normally fire here.
        State.MISSING_INFO,
        # Cascade's duplicates branch would normally fire here.
        State.DUPLICATE_REVIEW,
        # Terminal state with cascade fallthrough — guard still fires first.
        State.RESOLVED,
    ],
)
def test_other_category_escalates_regardless_of_state(state: State) -> None:
    """The guard fires regardless of what state the ticket is in."""
    ticket_state = _minimal_ticket_state_with_category(
        PrimaryCategory.OTHER,
        state=state,
    )
    result = get_next_action(ticket_state)
    assert result.type is RecommendedActionType.ESCALATE_TO_HUMAN


def test_other_category_preserves_human_review_flag() -> None:
    """requires_human_review is set to True on the OTHER path.

    The guard runs AFTER the human-review flag assignment, so an OTHER
    ticket that reaches get_next_action still gets the flag flipped
    regardless of what the caller supplied.
    """
    ticket_state = _minimal_ticket_state_with_category(
        PrimaryCategory.OTHER,
        requires_human_review=False,
    )
    get_next_action(ticket_state)
    assert ticket_state.requires_human_review is True


def test_other_category_writes_audit_entry() -> None:
    """The guard path writes an AuditEntry with OTHER-guard in the reason.

    Preserves the audit-trail invariant that every recommendation
    decision is recorded, so 1.2's short-circuit is reconstructable
    from the audit log the same way cascade decisions are.
    """
    ticket_state = _minimal_ticket_state_with_category(PrimaryCategory.OTHER)
    initial_audit_len = len(ticket_state.audit)
    get_next_action(ticket_state)
    assert len(ticket_state.audit) == initial_audit_len + 1
    last_reason = ticket_state.audit[-1].reason
    assert "OTHER" in last_reason
    assert "escalate_to_human" in last_reason
