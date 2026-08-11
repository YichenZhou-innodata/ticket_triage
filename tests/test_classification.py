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

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.enums import PrimaryCategory
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
