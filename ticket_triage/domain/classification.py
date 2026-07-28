"""classification.py

Classifies an incoming ticket into a PrimaryCategory using the loaded
rule book. Currently supports access_request only; extend by adding
rule books for additional categories.
"""

from ticket_triage.enums import PrimaryCategory


def classify_ticket(ticket_text: str) -> str:
    """Classify a single ticket into a primary category.

    Args:
        ticket_text: The raw text content of the incoming ticket.

    Returns:
        A string representing the ticket category.
    """
    return PrimaryCategory.ACCESS_REQUEST.value