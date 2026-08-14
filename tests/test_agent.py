"""test_agent.py

Unit tests for agent error handling and degraded fallbacks.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from google.genai.errors import APIError, ClientError

from ticket_triage.agent import safe_generate_recommendation
from ticket_triage.enums import RecommendedActionType
from ticket_triage.schema import TicketState


@pytest.fixture
def sample_ticket():
    """Load a real sample ticket from JSON using an absolute path relative to this test file."""
    base_dir = Path(__file__).resolve().parent.parent
    sample_path = base_dir / "ticket_triage" / "data" / "sample_tickets.jsonl"
    
    if not sample_path.exists():
        sample_path = base_dir / "data" / "sample_tickets.jsonl"

    with sample_path.open("r", encoding="utf-8") as f:
        first_line = f.readline()
        raw_dict = json.loads(first_line)
    return TicketState.model_validate(raw_dict)


def test_rate_limit_429_fallback(sample_ticket):
    """429 RESOURCE_EXHAUSTED returns rate-limited degraded response."""
    mock_client = MagicMock()
    # Instantiate ClientError using positional argument for message
    err = ClientError(429, "RESOURCE_EXHAUSTED: Quota exceeded")
    mock_client.models.generate_content.side_effect = err

    rec = safe_generate_recommendation(sample_ticket, client=mock_client)

    assert rec.type == RecommendedActionType.ESCALATE_TO_HUMAN
    assert "rate-limited" in rec.message.lower()
    assert sample_ticket.requires_human_review is True


def test_general_client_error_fallback(sample_ticket):
    """Non-429 ClientError returns generic unavailable response."""
    mock_client = MagicMock()
    err = ClientError(400, "Invalid Argument")
    mock_client.models.generate_content.side_effect = err

    rec = safe_generate_recommendation(sample_ticket, client=mock_client)

    assert rec.type == RecommendedActionType.ESCALATE_TO_HUMAN
    assert "unavailable" in rec.message.lower()
    assert sample_ticket.requires_human_review is True


def test_network_error_fallback(sample_ticket):
    """Transport and connection errors trigger degraded human escalation."""
    mock_client = MagicMock()
    mock_client.models.generate_content.side_effect = ConnectionError("Connection refused")

    rec = safe_generate_recommendation(sample_ticket, client=mock_client)

    assert rec.type == RecommendedActionType.ESCALATE_TO_HUMAN
    assert "network" in rec.message.lower() or "unavailable" in rec.message.lower()
    assert sample_ticket.requires_human_review is True