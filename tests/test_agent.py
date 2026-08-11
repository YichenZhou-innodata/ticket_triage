"""test_agent.py

Tests the composed instruction and tool registration on ``root_agent``.

These tests do NOT invoke the LLM — they check the static wiring only:
which tools are registered, and whether the instruction text carries
the guidance the model needs (OTHER-category branching, escalation
tool name). Live model behavior is out of scope; the guard in
``recommendation.py`` is what enforces correctness when the model
ignores the instruction.
"""

from ticket_triage.agent import root_agent
from ticket_triage.domain.classification import (
    classify_ticket,
    escalate_unsupported_ticket,
)
from ticket_triage.domain.recommendation import get_next_action


def test_agent_registers_classify_ticket() -> None:
    """classify_ticket is registered as a tool."""
    assert classify_ticket in root_agent.tools


def test_agent_registers_get_next_action() -> None:
    """get_next_action is registered as a tool."""
    assert get_next_action in root_agent.tools


def test_agent_registers_escalate_unsupported_ticket() -> None:
    """escalate_unsupported_ticket is registered as a tool (item 1.2)."""
    assert escalate_unsupported_ticket in root_agent.tools


def test_instruction_mentions_other_category() -> None:
    """The composed instruction must tell the model OTHER is a possible
    classification outcome."""
    assert "other" in root_agent.instruction.lower()


def test_instruction_names_the_escalation_tool() -> None:
    """The composed instruction must direct the model to call
    escalate_unsupported_ticket on the OTHER path."""
    assert "escalate_unsupported_ticket" in root_agent.instruction


def test_instruction_still_scoped_to_access_request() -> None:
    """The instruction still describes the access_request pipeline since
    that is the only supported category."""
    assert "access_request" in root_agent.instruction
