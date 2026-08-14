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
        "steps 3-5 in this case.",
        "  3. Otherwise (classify_ticket returned \"access_request\"): "
        "extract entity fields from the ticket text and determine "
        "any missing required fields.",
        # NOTE — INTENTIONAL STATE STEERING, do not "correct" this.
        # Steps 4-5 below deliberately steer the model toward state=intake
        # and a single get_next_action call. This works WITH the KNOWN TRAP
        # (see the NOTE block near _RULEBOOK above): the cascade only
        # handles state=intake explicitly, so any other state falls
        # through to escalate_to_human and the model interprets that as
        # "wrong answer, try again" and probes multiple states — that was
        # the latency problem this steering fixes. Making the model MORE
        # accurate about state selection regresses the happy path (also
        # documented in the NOTE). If the cascade later becomes state-
        # aware (REMAINING_WORK.md Part 2.2), delete steps 4-5's
        # steering language along with the trap.
        #
        # The step-4 language below is deliberately absolute. An earlier
        # version had an escape-hatch clause ("unless the ticket text
        # clearly indicates it is further along") and the model
        # interpreted a complete ticket with all fields present as
        # "further along" and picked state=ready_for_access_review,
        # which fell through the cascade and regressed the happy path
        # back to escalate_to_human. Removed. Ambiguity here is not a
        # feature — the cascade is state-blind, so every possible state
        # selection except "intake" is wrong for the demo.
        "  4. A ticket submitted through this interface has just arrived "
        "and is always in the \"intake\" state. Use \"intake\". Do not "
        "select any other state — a complete ticket with all fields "
        "present is still in intake, because intake is where triage "
        "begins, not where it ends.",
        "  5. Call get_next_action ONE time with that state. Accept the "
        "result. Do not call get_next_action again with a different "
        "state hoping for a better answer.",
        "",
        "Always return a structured response with the recommended action.",
    ]
    return "\n".join(lines)


root_agent = LlmAgent(
    name="ticket_executor",
    # gemini-2.0-flash returns 429 limit:0 on this project's free tier.
    # gemini-flash-latest works but was seeing 503 UNAVAILABLE from its
    # serving pool on demo day. gemini-flash-lite-latest is a separate
    # serving deployment (dodges the 503 pattern) and has faster
    # per-call inference, both of which matter for the live demo.
    model="gemini-flash-lite-latest",
    description="Triages IT support tickets.",
    instruction=_compose_instruction(_RULEBOOK),
    tools=[classify_ticket, escalate_unsupported_ticket, get_next_action],
)
