"""run_recommendations.py

Research / demo script — NOT part of the executor pipeline.

Runs the executor's existing rules-based recommendation logic
(`ticket_triage.domain.recommendation.get_next_action`) against every ticket
in `ticket_triage/data/sample_tickets.jsonl` and prints a table comparing
what the rules engine recommends against the ground-truth
`recommended_action.type` stored on each sample ticket.

This exercises Arya's actual code on `main`. No LLM call. No API key.
Purely deterministic — good for regression testing and for measuring how
well the current rule cascade covers the 10 sample scenarios.

Run from the repo root:
  .venv/Scripts/python.exe scripts/run_recommendations.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SAMPLE_PATH = REPO_ROOT / "ticket_triage" / "data" / "sample_tickets.jsonl"


def main() -> int:
    """Entry point. Returns a process exit code."""
    # Import here so a fresh checkout can still --help without the package
    # being importable yet.
    from ticket_triage.domain.recommendation import get_next_action
    from ticket_triage.schema import TicketState

    lines = [
        line for line in SAMPLE_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    tickets = [TicketState.model_validate(json.loads(line)) for line in lines]

    print(f"Loaded {len(tickets)} tickets from {SAMPLE_PATH.name}\n")

    header = (
        f"{'ID':<12} {'State':<25} {'Missing':<20} "
        f"{'Ticket says (truth)':<26} {'get_next_action() says':<26} Match"
    )
    print(header)
    print("-" * len(header))

    matches = 0
    for ticket in tickets:
        recommended = get_next_action(ticket)
        truth = ticket.recommended_action.type
        agrees = recommended.type == truth
        matches += int(agrees)

        missing = ",".join(f.value for f in ticket.missing_fields) or "-"
        print(
            f"{ticket.issue_id:<12} "
            f"{ticket.state.value:<25} "
            f"{missing[:19]:<20} "
            f"{truth.value:<26} "
            f"{recommended.type.value:<26} "
            f"{'YES' if agrees else 'NO'}"
        )

    print()
    print(f"Agreement: {matches}/{len(tickets)} tickets have get_next_action() matching the sample-ticket ground truth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
