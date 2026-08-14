"""recommendation.py

Picks the next recommended action for a ticket
based on its current state and extracted entities.
"""

from ticket_triage.enums import (
    EntityField,
    Event,
    RecommendedActionType,
    State,
)
from ticket_triage.schema import (
    AuditEntry,
    Entities,
    RecommendedAction,
    TicketState,
)


def get_next_action(ticket_state: TicketState) -> RecommendedAction:
    """Determine the next recommended action for a ticket.

    Args:
        ticket_state: The current state of the ticket.

    Returns:
        A RecommendedAction with the suggested next step.

    Raises:
        ValueError: If the ticket is in an unhandled state.
    """
    # v1 copilot invariant: every recommendation is subject to human review.
    ticket_state.requires_human_review = True

    current_state = ticket_state.state
    state_val = current_state.value if hasattr(current_state, "value") else str(current_state)

    # =========================================================================
    # 2.2 DECISION CASCADE LOGIC
    # =========================================================================

    # 1. High-Priority State Branches (Checked BEFORE content/field checks)
    if state_val == State.STALE_WAITING_FOR_USER.value:
        branch = "stale_waiting_for_user"
        action = RecommendedAction(
            type=RecommendedActionType.SEND_FOLLOW_UP_REMINDER,
            message="Ticket is stale waiting for user response. Sending reminder.",
        )
    elif state_val == State.HUMAN_REVIEW.value:
        branch = "human_review"
        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message="Ticket requires human review.",
        )
    elif state_val == State.DENIED.value:
        branch = "denied"
        action = RecommendedAction(
            type=RecommendedActionType.DRAFT_DENIAL_COMMENT,  # Expected: draft_denial_comment
            message="Access request denied. Drafting denial comment for review.",
        )
    elif state_val in (State.RESOLVED.value, State.CLOSED.value):
        branch = "terminal_close"
        action = RecommendedAction(
            type=RecommendedActionType.CLOSE_TICKET,
            message=f"Ticket in terminal state {state_val}. Closing ticket.",
        )
    elif state_val == State.READY_FOR_ACCESS_REVIEW.value:
        branch = "ready_for_access_review"
        action = RecommendedAction(
            type=RecommendedActionType.REQUEST_APPROVAL,
            message="Ready for access review. Requesting approval.",
        )
    elif state_val == State.ACCESS_PROVISIONING.value:
        branch = "access_provisioning"
        action = RecommendedAction(
            type=RecommendedActionType.RECOMMEND_ROUTE_TO_ACCESS_ADMIN,  # Expected: route to access admin
            message="Access provisioning in progress. Routing to access admin.",
        )

    # 2. Reopened Ticket Check (Intake + Reopened event in audit or last_event)
    elif state_val == State.INTAKE.value and (
        ticket_state.last_event == Event.TICKET_REOPENED
        or any(
            getattr(entry, "event", None) == Event.TICKET_REOPENED
            for entry in getattr(ticket_state, "audit", [])
        )
    ):
        branch = "reopened_intake"
        action = RecommendedAction(
            type=RecommendedActionType.EXTRACT_FIELDS,
            message="Reopened ticket in intake. Re-extracting fields.",
        )

    # 3. Content-Based Checks (Evaluated during standard intake or unhandled states)
    elif ticket_state.missing_fields:
        branch = "missing_fields"
        missing_str = ", ".join(
            f.value if hasattr(f, "value") else str(f)
            for f in ticket_state.missing_fields
        )
        action = RecommendedAction(
            type=RecommendedActionType.ASK_FOR_MISSING_INFO,
            message=f"Missing required fields: {missing_str}",
        )
    elif ticket_state.duplicate_candidates:
        branch = "duplicate_candidates"
        action = RecommendedAction(
            type=RecommendedActionType.SUGGEST_DUPLICATE_REVIEW,
            message="Possible duplicate tickets found. Please review before proceeding.",
        )

    # 4. Fresh Intake Branch
    elif state_val == State.INTAKE.value:
        branch = "intake_state"
        action = RecommendedAction(
            type=RecommendedActionType.REQUEST_APPROVAL,
            message="All required fields present. Ready to route for approval.",
        )

    # 5. Default Fallthrough
    else:
        branch = "fallthrough"
        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=f"Unhandled state: {ticket_state.state}. Escalating to human review.",
        )

    # Log audit trail
    ticket_state.audit.append(
        AuditEntry(
            event=ticket_state.last_event,
            from_state=ticket_state.state,
            to_state=ticket_state.state,
            reason=(
                f"recommendation decision (not a state transition); "
                f"cascade branch={branch}; action={action.type.value}"
            ),
        )
    )
    return action