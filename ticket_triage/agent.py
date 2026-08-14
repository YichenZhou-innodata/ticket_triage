"""agent.py

Agent-orchestrated triage flow combining Gemini model calls with
rule book enforcement and recommendation fallback logic.
"""

import logging
from pathlib import Path
from typing import Optional

from google.genai.errors import APIError, ClientError

from ticket_triage.domain.recommendation import get_next_action
from ticket_triage.enums import RecommendedActionType
from ticket_triage.rulebook import Rulebook, load_rulebook
from ticket_triage.schema import AuditEntry, RecommendedAction, TicketState

logger = logging.getLogger(__name__)

# Find path relative to agent.py's location
_BASE_DIR = Path(__file__).resolve().parent
_RULEBOOK_PATH = _BASE_DIR / "templates" / "access_request_v1.json"

# Intentional fail-fast at import time: DO NOT wrap in try/except!
_RULEBOOK: Rulebook = load_rulebook(_RULEBOOK_PATH)


def safe_generate_recommendation(
    ticket_state: TicketState,
    client: Optional[object] = None,
) -> RecommendedAction:
    """Generate a recommendation using the agent model path with graceful error handling."""
    ticket_state.requires_human_review = True

    try:
        if client is not None:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Triage ticket: {ticket_state.issue_id}",
            )

        return get_next_action(ticket_state)

    except ClientError as err:
        logger.warning(f"Gemini ClientError for {ticket_state.issue_id}: {err}")
        code = getattr(err, "code", None) or getattr(err, "status_code", None)
        err_str = str(err).upper()

        if code == 429 or "RESOURCE_EXHAUSTED" in err_str or "RATE_LIMIT" in err_str:
            msg = "Service is temporarily rate-limited; the request has been queued for human review."
        else:
            msg = "Automated triage is unavailable; escalating to human review."

        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=msg,
        )
        ticket_state.audit.append(
            AuditEntry(
                event=ticket_state.last_event,
                from_state=ticket_state.state,
                to_state=ticket_state.state,
                reason=f"agent error fallback: {msg}",
            )
        )
        return action

    except APIError as err:
        logger.error(f"Gemini APIError for {ticket_state.issue_id}: {err}")
        msg = "Automated triage is unavailable; escalating to human review."
        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=msg,
        )
        ticket_state.audit.append(
            AuditEntry(
                event=ticket_state.last_event,
                from_state=ticket_state.state,
                to_state=ticket_state.state,
                reason=f"agent error fallback: {msg}",
            )
        )
        return action

    except (ConnectionError, TimeoutError, OSError) as err:
        logger.error(f"Network error during model triage for {ticket_state.issue_id}: {err}")
        msg = "Automated triage is unavailable due to network error; escalating to human review."
        action = RecommendedAction(
            type=RecommendedActionType.ESCALATE_TO_HUMAN,
            message=msg,
        )
        ticket_state.audit.append(
            AuditEntry(
                event=ticket_state.last_event,
                from_state=ticket_state.state,
                to_state=ticket_state.state,
                reason=f"agent error fallback: {msg}",
            )
        )
        return action