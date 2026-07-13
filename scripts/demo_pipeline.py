"""demo_pipeline.py

Visual walkthrough of the rules engine (`get_next_action`) processing every
sample ticket. Prints, per ticket, what the engine sees (state, extracted
entities, missing fields, duplicate candidates) and what it recommends —
compared against the ground-truth `recommended_action.type` on the ticket.
For each mismatch, prints the specific gap in the current cascade.

Deterministic. No API key. No LLM.

Run:
    .venv/Scripts/python.exe scripts/demo_pipeline.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Force UTF-8 so the box-drawing / check-marks render on the Windows console.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from ticket_triage.domain.recommendation import get_next_action  # noqa: E402
from ticket_triage.schema import Entities, TicketState  # noqa: E402


SAMPLE_PATH = REPO_ROOT / "ticket_triage" / "data" / "sample_tickets.jsonl"

# Human-readable reasons for the six known cascade gaps.
# Matches the xfail decorators in tests/test_recommendation.py.
KNOWN_GAPS: dict[str, str] = {
    "SAMPLE-001": "state-blind cascade: no branch for ready_for_access_review",
    "SAMPLE-006": "state-blind cascade: no branch for access_provisioning",
    "SAMPLE-007": "state-blind cascade: no branch for denied",
    "SAMPLE-008": "ordering bug: missing_fields is checked before state",
    "SAMPLE-009": "cannot distinguish fresh intake from reopened intake",
    "SAMPLE-010": "ordering bug: missing_fields is checked before state",
}

WIDTH = 75
DBL = "═" * WIDTH
THIN = "─" * WIDTH
LABEL_W = 19


def _synthesize_raw_text(e: Entities) -> str:
    """Build a plausible full reporter message from a ticket's entity fields."""
    lines = ["Subject: Access request", "", "Hi team,", ""]
    intro = ["Requesting access"]
    if e.user_role:
        intro.append(f"as a {e.user_role}")
    if e.portfolio:
        intro.append(f"to the {e.portfolio} portfolio")
    if e.region:
        intro.append(f"in the {e.region} region")
    lines.append(" ".join(intro) + ".")
    if e.name:
        lines.append(f"My name is {e.name}.")
    if e.employee_id:
        lines.append(f"Employee ID: {e.employee_id}.")
    if e.project_type:
        lines.append(f"This is for a {e.project_type} project.")
    if e.leads:
        lines.append(f"Approver: {', '.join(e.leads)}.")
    if e.additional_context:
        lines.extend(["", e.additional_context])
    lines.extend(["", "Thanks!"])
    return "\n".join(lines)


def _raw_preview(e: Entities, maxlen: int = 70) -> str:
    """Single-line, quoted, ellipsis-truncated version of the synthesized text."""
    text = _synthesize_raw_text(e).replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    text = text.strip()
    if len(text) > maxlen:
        text = text[: maxlen - 3] + "..."
    return f'"{text}"'


def _format_entities(e: Entities) -> str:
    """Populated-only 'k=v' summary of the entity fields."""
    parts: list[str] = []
    if e.name:
        parts.append(f"name={e.name}")
    if e.employee_id:
        parts.append(f"employee_id={e.employee_id}")
    if e.portfolio:
        parts.append(f"portfolio={e.portfolio}")
    if e.region:
        parts.append(f"region={e.region}")
    if e.user_role:
        parts.append(f"user_role={e.user_role}")
    if e.project_type:
        parts.append(f"project_type={e.project_type}")
    if e.leads:
        parts.append(f"leads={e.leads}")
    if e.additional_context:
        ctx = e.additional_context
        if len(ctx) > 35:
            ctx = ctx[:32] + "..."
        parts.append(f'context="{ctx}"')
    return ", ".join(parts) if parts else "(no entities extracted)"


def _format_missing(missing_fields: list) -> str:
    return ", ".join(f.value for f in missing_fields) if missing_fields else "(none)"


def _format_duplicates(candidates: list) -> str:
    if not candidates:
        return "no candidates"
    ids = ", ".join(c.issue_id for c in candidates)
    return f"{len(candidates)} candidate(s): {ids}"


def _labeled(label: str, value: str) -> str:
    return f"{label:<{LABEL_W}}{value}"


def walk_ticket(ticket: TicketState) -> bool:
    """Print a full walkthrough for one ticket. Returns True if rules match truth."""
    print(DBL)
    print(f"TICKET: {ticket.issue_id}")
    print(THIN)
    print(_labeled("Raw (synthesized):", _raw_preview(ticket.entities)))
    print(_labeled("State:", ticket.state.value))
    print(_labeled("Entities found:", _format_entities(ticket.entities)))
    print(_labeled("Missing fields:", _format_missing(ticket.missing_fields)))
    print(_labeled("Duplicate check:", _format_duplicates(ticket.duplicate_candidates)))
    print(THIN)

    recommended = get_next_action(ticket)
    expected = ticket.recommended_action.type
    matches = recommended.type is expected

    mark = "✓" if matches else "✗"
    reason = ""
    if not matches:
        gap = KNOWN_GAPS.get(ticket.issue_id, "unexpected mismatch (was previously passing?)")
        reason = f"  (rules engine gap: {gap})"

    print(f"→ RECOMMENDATION: {recommended.type.value}")
    print(f"→ EXPECTED:       {expected.value}")
    print(f"→ MATCH:          {mark}{reason}")
    print(DBL)
    return matches


def main() -> int:
    lines = [
        line for line in SAMPLE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    tickets = [TicketState.model_validate(json.loads(line)) for line in lines]
    print(f"Loaded {len(tickets)} sample tickets. Walking through each...\n")

    matches = 0
    for ticket in tickets:
        if walk_ticket(ticket):
            matches += 1
        print()

    print(DBL)
    print(
        f"SUMMARY: rules engine matched ground truth on "
        f"{matches}/{len(tickets)} tickets"
    )
    if matches < len(tickets):
        gaps_present = sum(1 for t in tickets if t.issue_id in KNOWN_GAPS)
        print(
            f"         {gaps_present} known cascade gaps documented in "
            f"tests/test_recommendation.py xfails"
        )
    print(DBL)
    return 0


if __name__ == "__main__":
    sys.exit(main())
