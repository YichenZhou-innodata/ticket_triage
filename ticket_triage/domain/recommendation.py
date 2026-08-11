"""recommendation.py

Picks the next recommended action for a ticket
based on its current state and extracted entities.
"""

from ticket_triage.enums import (
    EntityField,
    Event,
    PrimaryCategory,
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
    # Override whatever the caller supplied — the flag is a policy, not a hint.
    # NOTE: this enforces the invariant at the tool boundary. The LLM composes
    # its user-visible summary from its own constructed state, so the rendered
    # output may still show whatever the model decided. Closing that gap needs
    # a separate change (surfacing the flag in the tool return or the message
    # text) — out of scope for this fix.
    ticket_state.requires_human_review = True

    # OTHER-category guard — defense-in-depth backstop for item 1.2 of
    # REMAINING_WORK.md. When the classifier returns PrimaryCategory.OTHER
    # (a ticket that isn't an access request), the instruction tells the
    # model to call escalate_unsupported_ticket instead of get_next_action.
    # If the model ignores that instruction and calls get_next_action anyway,
    # this early return prevents the cascade from asking a bug reporter for
    # their employee_id (the exact original bug items 1.1/1.2 fix).
    #
    # Kept strictly as an early return before the cascade — the cascade
    # branches below are unchanged. Preserves the audit-trail invariant by
    # appending an AuditEntry before returning, so every recommendation
    # decision is recorded uniformly.
    if ticket_state.primary_category is PrimaryCategory.OTHER:
        other_action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=(
                "Ticket category is not access_request; escalating to "
                "human review without running the access-request cascade."
            ),
        )
        ticket_state.audit.append(
            AuditEntry(
                event=ticket_state.last_event,
                from_state=ticket_state.state,
                to_state=ticket_state.state,
                reason=(
                    "recommendation decision (not a state transition); "
                    "OTHER-category guard; action=escalate_to_human"
                ),
            )
        )
        return other_action

    if ticket_state.missing_fields:
        branch = "missing_fields"
        action = RecommendedAction(
            type=RecommendedActionType.ASK_FOR_MISSING_INFO,
            message=f"Missing required fields: {', '.join(ticket_state.missing_fields)}",
        )
    elif ticket_state.duplicate_candidates:
        branch = "duplicate_candidates"
        action = RecommendedAction(
            type=RecommendedActionType.SUGGEST_DUPLICATE_REVIEW,
            message="Possible duplicate tickets found. Please review before proceeding.",
        )
    elif ticket_state.state == State.INTAKE:
        branch = "intake_state"
        action = RecommendedAction(
            type=RecommendedActionType.REQUEST_APPROVAL,
            message="All required fields present. Ready to route for approval.",
        )
    else:
        branch = "fallthrough"
        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=f"Unhandled state: {ticket_state.state}. Escalating to human review.",
        )

    # Log which cascade branch fired so a wrong recommendation is reconstructable.
    # from_state == to_state because computing a recommendation is not itself a
    # state transition; the reason string calls this out so a reader does not
    # mistake these rows for actual state changes.
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
