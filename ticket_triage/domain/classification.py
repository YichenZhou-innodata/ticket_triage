"""classification.py

Classifies an incoming ticket into a ``PrimaryCategory``.

v1: rule-based keyword matching. Deterministic, testable without
quota, predictable in a demo. If the ticket text contains any of a
small set of access-request signal words, returns ``ACCESS_REQUEST``;
otherwise returns ``OTHER``.

Design tradeoffs — READ THIS BEFORE CHANGING THE KEYWORD SET
=============================================================

The keyword set has two parts:

1. **Verb / concept words** (``access``, ``permission``,
   ``permissions``, ``credentials``, ``login``, ``grant``,
   ``provision``, ``authorize``, ``authorization``). Unambiguous
   access-request signals; the false-positive surface is small.

2. **Role-level names** (``editor``, ``viewer``, ``admin``).
   Added because roughly 30% of the sample access-request tickets
   signal via a role name rather than the word "access" — e.g.
   ``"Editor on the M&A deal book"`` or
   ``"needs editor on the modeling workbook"``. Without these,
   the classifier misses common natural phrasings that a real
   reporter would write.

   **Known false positives from this addition** (pure keyword
   matching cannot distinguish these — the word is identical, only
   context differs):

   - ``"the text editor keeps crashing"`` → matches ``editor`` →
     ``ACCESS_REQUEST``. Actually a bug report about text-editing
     software.
   - ``"our admin approved the design"`` → matches ``admin`` →
     ``ACCESS_REQUEST``. Actually a status update mentioning an
     administrator.

   These are represented as expected-behavior tests in
   ``tests/test_classification.py`` (search for
   ``test_known_limitation``) so the tradeoff is visible to anyone
   who later "fixes" the tests without understanding why they exist.

3. **``analyst`` and ``reviewer`` deliberately excluded** — they
   read as job titles ("we need a new analyst") at least as often
   as they read as permission levels. ``editor`` / ``viewer`` /
   ``admin`` are unambiguously permission levels in this domain.

Escalation does NOT catch these false positives
------------------------------------------------

Item 1.2 in ``REMAINING_WORK.md`` adds a short-circuit that routes
``OTHER`` classifications straight to human review. That short-circuit
fires on ``OTHER``. It does **not** fire on a false-positive
``ACCESS_REQUEST``. So the false positives documented above will still
run down the access-request pipeline and end up asking the reporter for
missing entity fields (name, employee_id, etc.). That is the exact
original bug we are trying to fix, surviving for this specific class of
input. It's an accepted cost of the keyword tradeoff, not a gap the
1.2 short-circuit will paper over.

Path to fix this class of failure
----------------------------------

The natural upgrade is an LLM-based classifier that can reason about
context ("text editor" as software vs "editor role" as a permission
level). Deferred for v1 because:

- Adds a Gemini call per ticket (already 2-3 per invocation).
- Adds a failure mode (429, refusal, unparseable output).
- Nondeterministic — makes demos less predictable.
- Consumes quota that is already scarce.

If demo scenarios include the documented false positives, the answer
is either (a) don't use those exact phrasings in the demo, or
(b) accept the escalation-to-human that happens after the model tries
and fails to extract entities.
"""

import re

from ticket_triage.enums import PrimaryCategory, RecommendedActionType
from ticket_triage.rulebook import Rulebook
from ticket_triage.schema import RecommendedAction


_ACCESS_REQUEST_KEYWORDS = (
    # Verb / concept words — unambiguous access signals.
    "access",
    "permission",
    "permissions",
    "credentials",
    "login",
    "grant",
    "provision",
    "authorize",
    "authorization",
    # Role-level names — unambiguous permission levels in this domain.
    # See module docstring for the tradeoff (known false positives on
    # non-access contexts that happen to mention these words).
    "editor",
    "viewer",
    "admin",
)

# Word-boundary, case-insensitive match against the keyword allowlist.
# Word boundary matters: "accessible" (a different word about reachability)
# should not match "access".
_ACCESS_REQUEST_PATTERN = re.compile(
    r"\b(" + "|".join(_ACCESS_REQUEST_KEYWORDS) + r")\b",
    re.IGNORECASE,
)


def classify_ticket(ticket_text: str, rulebook: Rulebook) -> PrimaryCategory:
    """Classify a single ticket into a primary category.

    Args:
        ticket_text: The raw text content of the incoming ticket.
        rulebook: The loaded rule book. Accepted for tool-signature
            stability (see the NOTE block in ``ticket_triage/agent.py``)
            — not consulted by the keyword classifier itself. Changing
            this signature would trigger ADK's schema-builder path
            that is already emitting warnings; leaving the parameter
            intact avoids that regression risk.

    Returns:
        ``PrimaryCategory.ACCESS_REQUEST`` if ``ticket_text`` contains
        any access-request signal word (see the module docstring for
        the keyword set and its tradeoffs).
        ``PrimaryCategory.OTHER`` otherwise, including empty,
        whitespace-only, or missing input.
    """
    if not ticket_text or not ticket_text.strip():
        return PrimaryCategory.OTHER
    if _ACCESS_REQUEST_PATTERN.search(ticket_text):
        return PrimaryCategory.ACCESS_REQUEST
    return PrimaryCategory.OTHER


def escalate_unsupported_ticket(ticket_text: str) -> RecommendedAction:
    """Return an escalation action for a ticket whose category isn't handled.

    Called by the agent when ``classify_ticket`` returns
    ``PrimaryCategory.OTHER``. Does not construct a ``TicketState`` —
    the ticket is not a valid input to the access-request pipeline.
    The ``RecommendedAction`` of type ``ESCALATE_TO_HUMAN`` is the
    semantic equivalent of the ``requires_human_review`` invariant
    ``get_next_action`` enforces on the access-request path.

    Args:
        ticket_text: The raw ticket text. Accepted for tool-signature
            stability and for future context in the escalation message
            (e.g. logging) — the current implementation does not
            inspect it.

    Returns:
        A ``RecommendedAction`` of type ``ESCALATE_TO_HUMAN`` with a
        clear "not supported yet, routed for human review" message.
    """
    return RecommendedAction(
        type=RecommendedActionType.ESCALATE_TO_HUMAN,
        message=(
            "This ticket does not appear to be an access request. "
            "The automated triage system does not handle this ticket "
            "type yet; routing to a human for review."
        ),
    )
