"""test_classification.py

Tests ``ticket_triage.domain.classification.classify_ticket`` — the
keyword-based v1 classifier.

Test groups:

- Positive tests: realistic access-request phrasings → ``ACCESS_REQUEST``
- Sample-ticket coverage: every sample ticket's ``additional_context``
  classifies as ``ACCESS_REQUEST``
- Negative tests: clearly non-access phrasings → ``OTHER``
- Edge cases: empty, whitespace, boundary
- KNOWN LIMITATION tests: the two documented false-positive cases from
  the classifier's keyword tradeoff. These assert current behavior
  explicitly so that any change to the classifier that alters them
  forces the change author to acknowledge the tradeoff — see the
  ``classification.py`` module docstring for the full rationale.
"""

import json
from pathlib import Path

import pytest

from ticket_triage.domain.classification import (
    classify_ticket,
    escalate_unsupported_ticket,
)
from ticket_triage.enums import PrimaryCategory, RecommendedActionType
from ticket_triage.rulebook import load_rulebook


_REPO_ROOT = Path(__file__).resolve().parent.parent
_RULEBOOK_PATH = _REPO_ROOT / "ticket_triage" / "templates" / "access_request_v1.json"
_SAMPLE_PATH = _REPO_ROOT / "ticket_triage" / "data" / "sample_tickets.jsonl"


@pytest.fixture(scope="module")
def rulebook():
    """Load the access_request_v1 rule book once per module.

    The classifier does not consult the rule book, but the tool
    signature requires it — see ``classification.py`` docstring.
    """
    return load_rulebook(_RULEBOOK_PATH)


# ----------------------------------------------------------------------
# Positive tests — realistic access-request phrasings
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I need editor access to the Renewables portfolio",
        "Please grant me permission to view the reports",
        "Requesting access to the workbook",
        "Login credentials please",
        "Can you give me permissions for the shared drive",
        "Need admin on the wiki",
        "Please authorize my account for the dashboard",
        "Requesting authorization to view Q3 numbers",
        "Provision me as a viewer on the sustainability dashboard",
    ],
)
def test_realistic_access_request_phrasings_match(text, rulebook):
    """Text with clear access-request signals returns ACCESS_REQUEST."""
    assert classify_ticket(text, rulebook) is PrimaryCategory.ACCESS_REQUEST


# ----------------------------------------------------------------------
# Sample-ticket coverage — every sample's additional_context should match
# ----------------------------------------------------------------------


def _load_sample_contexts():
    """Return list of (issue_id, additional_context) pairs from the JSONL."""
    lines = _SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        if not line.strip():
            continue
        t = json.loads(line)
        out.append((t["issue_id"], t["entities"].get("additional_context", "") or ""))
    return out


@pytest.mark.parametrize("issue_id,text", _load_sample_contexts())
def test_every_sample_ticket_context_classifies_as_access_request(
    issue_id, text, rulebook
):
    """Every shipped sample ticket's additional_context returns ACCESS_REQUEST.

    If this fails, either a sample ticket was added with an
    additional_context that does not signal access (fix the fixture),
    or the keyword set was narrowed (understand why before fixing).
    """
    assert classify_ticket(text, rulebook) is PrimaryCategory.ACCESS_REQUEST, (
        f"{issue_id} additional_context did not classify as ACCESS_REQUEST: {text!r}"
    )


# ----------------------------------------------------------------------
# Negative tests — clearly non-access phrasings
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I found a bug in the quarterly report generator - "
        "when I export to PDF the numbers are cut off",
        "The application crashes when I click submit",
        "Feature request: add a filter option to the search page",
        "Why does the report show yesterday's numbers?",
        "Can you explain how the pricing calculation works?",
    ],
)
def test_non_access_text_classified_as_other(text, rulebook):
    """Bug reports, feature requests, and questions return OTHER."""
    assert classify_ticket(text, rulebook) is PrimaryCategory.OTHER


# ----------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------


def test_empty_string_returns_other(rulebook):
    """Empty input returns OTHER (no signal to classify)."""
    assert classify_ticket("", rulebook) is PrimaryCategory.OTHER


def test_whitespace_only_returns_other(rulebook):
    """Whitespace-only input returns OTHER."""
    assert classify_ticket("   \n\t  ", rulebook) is PrimaryCategory.OTHER


def test_case_insensitive_match(rulebook):
    """Matching is case-insensitive."""
    assert (
        classify_ticket("I need ACCESS to the portal", rulebook)
        is PrimaryCategory.ACCESS_REQUEST
    )


def test_word_boundary_prevents_substring_match(rulebook):
    """``accessible`` should not match ``access`` (different word)."""
    # No other keyword appears in this sentence.
    assert (
        classify_ticket("This feature is accessible from the URL", rulebook)
        is PrimaryCategory.OTHER
    )


def test_short_gibberish_returns_other(rulebook):
    """Content-free short text returns OTHER."""
    assert classify_ticket("asdfasdf hello thanks", rulebook) is PrimaryCategory.OTHER


# ----------------------------------------------------------------------
# KNOWN LIMITATION tests — the two documented false positives
#
# These assert the CURRENT behavior, which is NOT the DESIRED behavior.
# Pure keyword matching cannot distinguish "text editor" (software) from
# "editor on the M&A deal book" (a permission level) — the word is
# identical, only context differs. See the classification.py module
# docstring for the full tradeoff analysis and the reason these tests
# exist as-is.
#
# If you're changing the classifier and one of these tests starts
# failing, do NOT "fix" it by changing the assertion until you have
# read the module docstring and understand what tradeoff you are
# changing. The classifier could stop matching these on purpose (e.g.
# an LLM-based upgrade) — in which case the fix is to delete these
# tests and note the upgrade in the module docstring, not to weaken
# the assertions to expect OTHER.
# ----------------------------------------------------------------------


def test_known_limitation_text_editor_bug_report_false_positive(rulebook):
    """KNOWN LIMITATION — not the desired outcome.

    A bug report about text-editing software matches ``editor`` and
    classifies as ACCESS_REQUEST. Real user impact: the pipeline will
    ask this bug reporter for an employee_id.
    """
    assert (
        classify_ticket("the text editor keeps crashing", rulebook)
        is PrimaryCategory.ACCESS_REQUEST
    )


def test_known_limitation_admin_status_update_false_positive(rulebook):
    """KNOWN LIMITATION — not the desired outcome.

    A status update mentioning an administrator matches ``admin`` and
    classifies as ACCESS_REQUEST. Same underlying issue as the
    text-editor case: the word is present, the context isn't.
    """
    assert (
        classify_ticket("our admin approved the design", rulebook)
        is PrimaryCategory.ACCESS_REQUEST
    )


# ----------------------------------------------------------------------
# escalate_unsupported_ticket — the tool the agent calls when
# classify_ticket returned OTHER (item 1.2)
# ----------------------------------------------------------------------


def test_escalate_unsupported_ticket_returns_escalate_to_human_type():
    """The escalation tool returns action type ESCALATE_TO_HUMAN."""
    result = escalate_unsupported_ticket("some bug report text")
    assert result.type is RecommendedActionType.ESCALATE_TO_HUMAN


def test_escalate_unsupported_ticket_message_mentions_human_review():
    """The escalation message must make the human-review outcome clear."""
    result = escalate_unsupported_ticket("some bug report text")
    lowered = result.message.lower()
    assert "human" in lowered or "review" in lowered
    assert len(result.message) > 20


def test_escalate_unsupported_ticket_ignores_input_text():
    """The current implementation does not inspect ticket_text — the
    signature accepts it for stability and future use only."""
    r1 = escalate_unsupported_ticket("bug in the export feature")
    r2 = escalate_unsupported_ticket("completely different content")
    assert r1.message == r2.message
    assert r1.type == r2.type


# ----------------------------------------------------------------------
# Input edge cases and non-English routing (item 1.3)
#
# The 1.3 audit found that 1.1 and 1.2 together already covered the
# meaningful input gaps (empty, whitespace, OTHER short-circuit at both
# instruction and code). The tests below are REGRESSION GUARDS — they
# pin the current behavior for input classes that aren't explicitly
# tested elsewhere, so a future keyword-set change or LLM-classifier
# upgrade cannot silently regress the escalation path for these inputs.
#
# Scope decision recorded in REMAINING_WORK.md: no Python-side length
# cap is added at the tool boundary. A cap that runs after the model
# call already happened does not prevent the cost it appears to prevent
# and gives a reader false confidence. See the item 1.3 section for the
# full reasoning.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        # Spanish access request — no English keyword present.
        "Necesito acceso al portal de proyectos",
        # French bug-report-like text — no English keyword present.
        "Le rapport ne fonctionne pas correctement",
        # Chinese (CJK): general request — unicode / non-latin safety.
        "我需要登录访问报告",
        # Arabic (RTL script): general request — RTL / non-latin safety.
        "أحتاج إلى الوصول",
    ],
)
def test_non_english_input_classifies_as_other(text, rulebook):
    """Non-English tickets deliberately route to OTHER → escalation.

    See classification.py's "Non-English input" docstring section for
    why this is correct behavior, not a gap. A human reviewer picking
    up the escalation can triage the ticket in its native language.
    """
    assert classify_ticket(text, rulebook) is PrimaryCategory.OTHER


def test_mixed_english_and_spanish_matches_via_english_keyword(rulebook):
    """English-mixed content (common in enterprise Spanglish) still routes
    through the access-request pipeline via the English keyword."""
    assert (
        classify_ticket("Necesito access al portal", rulebook)
        is PrimaryCategory.ACCESS_REQUEST
    )


@pytest.mark.parametrize(
    "text",
    [
        "hi",  # single word, non-keyword
        "!!!???",  # punctuation only
        "12345",  # digits only
    ],
)
def test_short_non_signal_input_returns_other(text, rulebook):
    """Very short content-free input returns OTHER (no signal to classify)."""
    assert classify_ticket(text, rulebook) is PrimaryCategory.OTHER


def test_very_long_input_with_keyword_still_matches(rulebook):
    """Regex handles long inputs without crashing or timing out.

    This is a smoke test for the "doesn't blow up" property — NOT a
    length-limit test. The scope decision to not enforce a Python-side
    length cap on ticket_text is documented in REMAINING_WORK.md item
    1.3. Realistic ticket sizes are well below this; the 100k figure
    is a "if someone paste-bombed" guard.
    """
    filler = "lorem ipsum " * 10_000  # ~120k characters
    text = filler + "please grant access"
    assert classify_ticket(text, rulebook) is PrimaryCategory.ACCESS_REQUEST
