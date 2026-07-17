"""test_sample_tickets.py

Tests that `ticket_triage/data/sample_tickets.jsonl` validates against
`TicketState` and covers the 10 triage scenarios listed in the PR scope:

a. Happy path
b. Missing employee_id only
c. Missing multiple fields
d. Duplicate candidate
e. Approver missing (leads empty)
f. Approval granted
g. Approval denied
h. Stale (no user response)
i. Reopened (audit shows prior closure + reopen)
j. Ambiguous edge case (low confidence)

Loading is delegated to `ticket_triage.sample_tickets.load_sample_tickets`,
which fails soft per-line. Since the shipped JSONL is a committed artifact,
`test_no_skipped_lines_in_shipped_file` asserts that zero lines are skipped
against it — invalid rows would fail loudly in that test, not silently.
"""

from pathlib import Path

import pytest

from ticket_triage.enums import (
    ApprovalStatus,
    EntityField,
    Event,
    PrimaryCategory,
    State,
)
from ticket_triage.sample_tickets import LoadResult, load_sample_tickets
from ticket_triage.schema import TicketState


SAMPLE_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "ticket_triage"
    / "data"
    / "sample_tickets.jsonl"
)


@pytest.fixture(scope="module")
def load_result() -> LoadResult:
    """Module-scoped fixture: load the shipped JSONL once."""
    return load_sample_tickets(SAMPLE_PATH, warn=False)


@pytest.fixture(scope="module")
def tickets(load_result: LoadResult) -> list[TicketState]:
    """Module-scoped fixture: the successfully-loaded tickets."""
    return load_result.tickets


# -- File presence & shape --------------------------------------------------


def test_sample_file_exists() -> None:
    """The sample tickets JSONL file is on disk."""
    assert SAMPLE_PATH.is_file(), f"Missing sample file at {SAMPLE_PATH}"


def test_no_skipped_lines_in_shipped_file(load_result: LoadResult) -> None:
    """
    The shipped JSONL is a committed artifact: every line MUST validate.
    If this fails, a row in sample_tickets.jsonl has become invalid.
    """
    if load_result.skipped_count > 0:
        detail = "\n".join(
            f"  line {s.line_number}: {s.reason}" for s in load_result.skipped
        )
        pytest.fail(
            f"{load_result.skipped_count} of {load_result.total_seen} rows "
            f"in sample_tickets.jsonl failed to load:\n{detail}"
        )


def test_at_least_ten_tickets(tickets: list[TicketState]) -> None:
    """The PR scope calls for ~10 tickets covering all 10 scenarios."""
    assert len(tickets) >= 10, f"Expected at least 10 tickets, got {len(tickets)}"


# -- Cross-ticket invariants -------------------------------------------------


def test_all_issue_ids_unique(tickets: list[TicketState]) -> None:
    """Every ticket has a distinct issue_id."""
    ids = [t.issue_id for t in tickets]
    assert len(ids) == len(set(ids)), f"Duplicate issue_ids in: {ids}"


def test_all_rulebook_access_request_v1(tickets: list[TicketState]) -> None:
    """All tickets reference the access_request_v1 rule book."""
    for ticket in tickets:
        assert ticket.rulebook == "access_request_v1"


def test_all_primary_category_access_request(tickets: list[TicketState]) -> None:
    """All tickets are tagged with the access_request primary category."""
    for ticket in tickets:
        assert ticket.primary_category is PrimaryCategory.ACCESS_REQUEST


# -- Scenario coverage ------------------------------------------------------


def test_coverage_happy_path(tickets: list[TicketState]) -> None:
    """(a) At least one ticket is in ready_for_access_review with no missing fields."""
    matches = [
        t
        for t in tickets
        if t.state is State.READY_FOR_ACCESS_REVIEW and not t.missing_fields
    ]
    assert matches, "no happy-path ticket (ready_for_access_review, missing_fields=[])"


def test_coverage_missing_employee_id_only(tickets: list[TicketState]) -> None:
    """(b) At least one missing_info ticket has only employee_id missing."""
    matches = [
        t
        for t in tickets
        if t.state is State.MISSING_INFO
        and t.missing_fields == [EntityField.EMPLOYEE_ID]
    ]
    assert matches, "no ticket with only employee_id missing"


def test_coverage_missing_multiple_fields(tickets: list[TicketState]) -> None:
    """(c) At least one missing_info ticket has 2+ missing fields."""
    matches = [
        t
        for t in tickets
        if t.state is State.MISSING_INFO and len(t.missing_fields) >= 2
    ]
    assert matches, "no ticket with multiple missing fields"


def test_coverage_duplicate_candidates(tickets: list[TicketState]) -> None:
    """(d) At least one ticket is in duplicate_review with populated candidates."""
    matches = [
        t
        for t in tickets
        if t.state is State.DUPLICATE_REVIEW and t.duplicate_candidates
    ]
    assert matches, "no duplicate_review ticket with candidates"


def test_coverage_approver_missing(tickets: list[TicketState]) -> None:
    """(e) At least one missing_info ticket lists leads as a missing field."""
    matches = [
        t
        for t in tickets
        if t.state is State.MISSING_INFO and EntityField.LEADS in t.missing_fields
    ]
    assert matches, "no ticket flagging leads as missing"


def test_coverage_approval_granted(tickets: list[TicketState]) -> None:
    """(f) At least one ticket has approval.status=granted in access_provisioning."""
    matches = [
        t
        for t in tickets
        if t.state is State.ACCESS_PROVISIONING
        and t.approval.status is ApprovalStatus.GRANTED
    ]
    assert matches, "no granted-approval ticket"


def test_coverage_denied(tickets: list[TicketState]) -> None:
    """(g) At least one denied ticket carries an audit entry explaining the denial."""
    matches = [
        t
        for t in tickets
        if t.state is State.DENIED
        and t.approval.status is ApprovalStatus.DENIED
        and any(a.event is Event.APPROVAL_DENIED for a in t.audit)
    ]
    assert matches, "no denied ticket with an approval_denied audit entry"


def test_coverage_stale(tickets: list[TicketState]) -> None:
    """(h) At least one ticket is stale with last_event=no_user_response."""
    matches = [
        t
        for t in tickets
        if t.state is State.STALE_WAITING_FOR_USER
        and t.last_event is Event.NO_USER_RESPONSE
    ]
    assert matches, "no stale ticket"


def test_coverage_reopened(tickets: list[TicketState]) -> None:
    """(i) At least one intake-state ticket has a ticket_reopened audit entry."""
    matches = [
        t
        for t in tickets
        if t.state is State.INTAKE
        and any(a.event is Event.TICKET_REOPENED for a in t.audit)
    ]
    assert matches, "no reopened ticket"


def test_coverage_ambiguous_edge_case(tickets: list[TicketState]) -> None:
    """(j) At least one ticket has low confidence (< 0.5)."""
    matches = [t for t in tickets if t.confidence < 0.5]
    assert matches, "no low-confidence ticket for ambiguous edge case"
