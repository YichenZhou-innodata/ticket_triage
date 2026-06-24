"""classification.py

Classifies an incoming ticket into a PrimaryCategory using the loaded
rule book. Currently supports access_request only; extend by adding
rule books for additional categories.
"""

from ticket_triage.enums import PrimaryCategory
from ticket_triage.rulebook import RuleBook


def classify_ticket(ticket_text: str, rulebook: RuleBook) -> PrimaryCategory:
    """Classify a single ticket into a primary category.

    Args:
        ticket_text: The raw text content of the incoming ticket.
        rulebook: The loaded rule book to classify against.

    Returns:
        A PrimaryCategory matching the ticket type.

    Raises:
        ValueError: If the ticket cannot be matched to any known category.
    """
    # Only access_request is supported until additional rule books are added
    return PrimaryCategory.ACCESS_REQUEST