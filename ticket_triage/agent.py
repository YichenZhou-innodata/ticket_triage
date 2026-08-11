"""agent.py

Entry point for the ticket triage ADK agent. Wires up the LlmAgent with
Gemini and registers the classification and recommendation tools.

The rule book at ``ticket_triage/templates/access_request_v1.json`` is
loaded at module import and its concrete facts (states, allowed events
per state, allowed actions per state, required and provisional entity
fields) are composed into the agent's instruction so the model reasons
with real values rather than fabricating them.

The full analysis of why the deterministic cascade is NOT rewritten to
be data-driven — and why the live happy path currently works only
because two bugs cancel each other out — is documented in the ``NOTE``
block just above ``_RULEBOOK`` below. That comment is the map for
whoever picks this up next; read it before touching the cascade.
"""

from pathlib import Path

from google.adk.agents import LlmAgent

from ticket_triage.domain.classification import (
    classify_ticket,
    escalate_unsupported_ticket,
)
from ticket_triage.domain.recommendation import get_next_action
from ticket_triage.enums import State
from ticket_triage.rulebook import Rulebook, load_rulebook


_RULEBOOK_PATH = (
    Path(__file__).resolve().parent / "templates" / "access_request_v1.json"
)


# NOTE — TWO BUGS CANCELLING OUT (the map for whoever fixes this next):
#
# 1. The cascade in ``ticket_triage.domain.recommendation.get_next_action``
#    only handles ``state == intake`` with an explicit positive branch.
#    All 12 other states fall through to ``escalate_to_human`` unless
#    ``missing_fields`` or ``duplicate_candidates`` short-circuits earlier.
#    Documented as audit finding F5 and pinned by 6 xfails in
#    ``tests/test_recommendation.py``.
#
# 2. The model, when triaging a ticket, tends to default to
#    ``state=intake`` for anything it isn't sure about. This lazy default
#    masks bug #1: the cascade's ``state == intake`` branch fires,
#    returns ``request_approval``, and the happy path appears to work.
#
# The two bugs cancel each other out in the live demo. That is the ONLY
# reason the current happy path works.
#
# ------------------------------------------------------------------
# What blocks a proper fix:
#
# - The rule book declares
#       allowed_actions_per_state[intake]
#           = ['extract_fields', 'suggest_duplicate_review']
#   It does NOT list ``request_approval`` — that action is allowed only
#   under ``ready_for_access_review``. So a data-driven get_next_action
#   that reads from the rule book cannot legitimately return
#   ``request_approval`` when ``state == intake``.
#
# - A prompt nudge was tested and DELIBERATELY WITHHELD from the
#   instruction below. The nudge said, in effect, "choose the current
#   state carefully; do not default to intake unless the ticket is
#   genuinely at the start of triage." Adding it makes the model more
#   accurate about state selection — happy-path tickets shift from
#   ``state=intake`` to ``state=ready_for_access_review``. At that
#   point the cascade's ``state == intake`` branch no longer fires,
#   the cascade falls through, and the happy path regresses to
#   ``escalate_to_human``. Making the model MORE correct would break
#   the demo. So the nudge is intentionally absent; bug #2 is
#   preserved so bug #1 stays masked.
#
# - Fixing this properly means (a) resolving the semantic disagreement
#   between the rule book and the cascade about what ``state=intake``
#   means and which state should trigger ``request_approval`` (a rule
#   book decision, needs coordination with the spec author), and then
#   (b) rewriting get_next_action to consult
#   ``allowed_actions_per_state`` from the rule book instead of the
#   hardcoded 3-branch cascade. Neither is done here.
#
# ------------------------------------------------------------------
# Observed live behavior (post-change):
#
# - With all 13 states in the instruction, the model probes
#   ``state='new'`` first (falls through to ``escalate_to_human``),
#   then retries with ``state='intake'`` (hits the one handled
#   branch). Costs an extra tool round-trip per invocation. Not fixed
#   here — a prompt nudge toward better state selection was tested
#   and withheld, since more accurate state selection exposes the
#   cascade gap and regresses the happy path (see above).
#
# - Extraction imprecision: the model concatenated project stage and
#   project name into ``project_type='active solar PV project'`` where
#   the schema expects just the stage (e.g. ``'active'``). Suggests
#   the instruction below would benefit from describing what each
#   entity field means. Not fixed here — noting for a follow-up.
#
# ------------------------------------------------------------------
# What this change DOES do:
#
# Loading the rule book at module import is worthwhile in its own
# right: the instruction composed below carries real state/action/event
# facts to the model instead of the model fabricating them in tool-call
# arguments (previously observed: the model was inventing partial
# rulebook dicts with 1 of 11 transitions). The cascade and the tool
# signatures are unchanged.
_RULEBOOK: Rulebook = load_rulebook(_RULEBOOK_PATH)


def _compose_instruction(rb: Rulebook) -> str:
    """Build the agent instruction string from live rule-book data.

    Args:
        rb: The loaded rule book. States, events, actions, and required
            fields are read directly from it so the instruction reflects
            what is currently on disk.

    Returns:
        A multi-line instruction string suitable for ``LlmAgent.instruction``.
    """
    # Preserve the State enum's declaration order (happy-path states first,
    # then off-ramps). Alphabetical would scramble the natural reading order.
    states = [s for s in State if s in rb.allowed_events_per_state]
    lines = [
        (
            "You are a ticket triage agent. You handle access_request "
            "tickets; other ticket types are escalated to a human."
        ),
        "",
        "Known states in the triage state machine:",
        *[f"  - {s.value}" for s in states],
        "",
        "Actions you may recommend, by state:",
        *[
            f"  - {s.value}: "
            f"{[a.value for a in rb.allowed_actions_per_state.get(s, [])]}"
            for s in states
        ],
        "",
        "Events that are valid inputs, by state:",
        *[
            f"  - {s.value}: "
            f"{[e.value for e in rb.allowed_events_per_state.get(s, [])]}"
            for s in states
        ],
        "",
        "Entity fields tracked for access_request:",
        f"  - Spec-confirmed as required: "
        f"{[f.value for f in rb.required_fields]}",
        f"  - Provisional (pending confirmation): "
        f"{[f.value for f in rb.provisional_required_fields]}",
        "",
        "When given a ticket:",
        "  1. Call classify_ticket with the ticket text.",
        "  2. If classify_ticket returned \"other\": call "
        "escalate_unsupported_ticket with the ticket text and return "
        "the recommended action from that tool. Do NOT proceed to "
        "steps 3-4 in this case.",
        "  3. Otherwise (classify_ticket returned \"access_request\"): "
        "determine the current state and any missing required fields.",
        "  4. Call get_next_action with the current state.",
        "",
        "Always return a structured response with the recommended action.",
    ]
    return "\n".join(lines)


root_agent = LlmAgent(
    name="ticket_executor",
    # gemini-2.0-flash returns 429 limit:0 on this project's free tier.
    # gemini-flash-latest is the ADK-recommended alias with working quota.
    model="gemini-flash-latest",
    description="Triages IT support tickets.",
    instruction=_compose_instruction(_RULEBOOK),
    tools=[classify_ticket, escalate_unsupported_ticket, get_next_action],
)
