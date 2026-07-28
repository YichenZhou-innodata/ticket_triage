"""recommendation.py

Walks the state machine and picks the next recommended action for a ticket
based on its current state and extracted entities.
"""


def get_next_action(missing_fields: str, has_duplicates: bool, current_state: str) -> str:
    """Determine the next recommended action for a ticket.

    Args:
        missing_fields: Comma-separated list of missing required fields, or empty string if none.
        has_duplicates: Whether duplicate tickets were found.
        current_state: The current state of the ticket.

    Returns:
        A string describing the recommended next action.
    """
    if missing_fields:
        return f"ASK_FOR_MISSING_INFO: Missing required fields: {missing_fields}"

    if has_duplicates:
        return "SUGGEST_DUPLICATE_REVIEW: Possible duplicate tickets found. Please review before proceeding."

    if current_state == "intake":
        return "REQUEST_APPROVAL: All required fields present. Ready to route for approval."

    return f"ESCALATE_TO_HUMAN: Unhandled state: {current_state}. Escalating to human review."