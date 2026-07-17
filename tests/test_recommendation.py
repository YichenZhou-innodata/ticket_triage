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
from ticket_triage.enums import RecommendedActionType
from ticket_triage.schema import TicketState


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
