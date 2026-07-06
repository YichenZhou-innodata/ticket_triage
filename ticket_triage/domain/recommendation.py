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
    if ticket_state.missing_fields:
        return RecommendedAction(
            type=RecommendedActionType.ASK_FOR_MISSING_INFO,
            message=f"Missing required fields: {', '.join(ticket_state.missing_fields)}",
        )

    if ticket_state.duplicate_candidates:
        return RecommendedAction(
            type=RecommendedActionType.SUGGEST_DUPLICATE_REVIEW,
            message="Possible duplicate tickets found. Please review before proceeding.",
        )

    if ticket_state.state == State.INTAKE:
        return RecommendedAction(
            type=RecommendedActionType.REQUEST_APPROVAL,
            message="All required fields present. Ready to route for approval.",
        )

    return RecommendedAction(
        type=RecommendedActionType.ESCALATE_TO_HUMAN,
        message=f"Unhandled state: {ticket_state.state}. Escalating to human review.",
    )