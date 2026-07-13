"""prototype_classify.py

Research / demo script — NOT part of the executor pipeline.

Loads the 10 sample tickets from `ticket_triage/data/sample_tickets.jsonl`,
synthesizes a realistic "raw reporter message" from each ticket's entity
fields (omitting fields the reporter didn't provide), and asks Gemini to
classify + extract entities + guess whether it looks like a duplicate.
Prints a table of what Gemini says for each ticket.

This is a REFERENCE for what real classification could look like — it does
not replace `ticket_triage/domain/classification.py` (currently a stub) and
does not touch `ticket_triage/agent.py`. It is a separate demo file living
under `scripts/` so it's clearly outside the executor pipeline.

Requires:
  - `.env` at the repo root containing `GOOGLE_API_KEY=<AI Studio key>`.
    An AI Studio key starts with `AIza`. If your key does not, this script
    will refuse to call Gemini and exit with a clear message rather than
    burning through a request that would 401.

Run from the repo root:
  .venv/Scripts/python.exe scripts/prototype_classify.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
SAMPLE_PATH = REPO_ROOT / "ticket_triage" / "data" / "sample_tickets.jsonl"
MODEL = "gemini-2.0-flash"

PROMPT_TEMPLATE = """You are a support-ticket triage assistant. Read the raw ticket text below and extract structured information.

Available primary categories:
- access_request

Entity fields to look for:
- name (the requester's full name)
- employee_id
- portfolio (business unit or product area)
- region (e.g. EMEA, APAC, AMER, LATAM)
- user_role (e.g. Viewer, Editor, Admin, Analyst)
- project_type (e.g. active, pre-planning, archived, in-flight, completed)
- leads (approving lead names)
- additional_context (any other useful context)

Return ONLY a JSON object with these fields, no prose, no code fences:
{{
  "primary_category": "access_request" or "unknown",
  "entities_present": [list of entity field names that appear in the text],
  "entities_missing": [list of entity field names that are absent],
  "looks_like_duplicate": true or false,
  "duplicate_reason": "brief reason if true, else null",
  "confidence": a number between 0.0 and 1.0
}}

Ticket text:
---
{ticket_text}
---
"""


def build_raw_ticket(entities: dict) -> str:
    """Synthesize a realistic 'raw reporter message' from a ticket's entities.

    Entity fields that are empty strings or empty lists are OMITTED, mimicking
    a real reporter who left them out. This is what makes a ticket look
    'missing_info' vs. 'complete' from the LLM's perspective.

    Args:
        entities: The dict of entity field values from a sample ticket.

    Returns:
        A multi-line string that reads like a support ticket body.
    """
    lines = ["Subject: Access request", "", "Hi team,", ""]

    intro = ["Requesting access"]
    if entities.get("user_role"):
        intro.append(f"as a {entities['user_role']}")
    if entities.get("portfolio"):
        intro.append(f"to the {entities['portfolio']} portfolio")
    if entities.get("region"):
        intro.append(f"in the {entities['region']} region")
    lines.append(" ".join(intro) + ".")

    if entities.get("name"):
        lines.append(f"My name is {entities['name']}.")
    if entities.get("employee_id"):
        lines.append(f"Employee ID: {entities['employee_id']}.")
    if entities.get("project_type"):
        lines.append(f"This is for a {entities['project_type']} project.")
    if entities.get("leads"):
        lines.append(f"Approver: {', '.join(entities['leads'])}.")
    if entities.get("additional_context"):
        lines.extend(["", entities["additional_context"]])

    lines.extend(["", "Thanks!"])
    return "\n".join(lines)


def classify_with_gemini(client, ticket_text: str) -> dict:
    """Call Gemini and parse a JSON response into a dict.

    Args:
        client: A `google.genai.Client` instance.
        ticket_text: The synthesized raw ticket text.

    Returns:
        The parsed JSON response, or a dict `{"error": ..., "raw": ...}` if
        the response could not be parsed.
    """
    prompt = PROMPT_TEMPLATE.format(ticket_text=ticket_text)
    response = client.models.generate_content(model=MODEL, contents=prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.strip("`").lstrip("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "Gemini did not return valid JSON", "raw": text[:200]}


def main() -> int:
    """Entry point. Returns a process exit code."""
    load_dotenv(REPO_ROOT / ".env", override=True)

    import os

    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key or key == "your-key-here":
        print(
            "ERROR: GOOGLE_API_KEY in .env is unset or still the placeholder. "
            "Paste your key into .env and rerun.",
            file=sys.stderr,
        )
        return 2

    try:
        from google import genai
    except ImportError:
        print("ERROR: google-genai not installed. Run `pip install -r requirements.txt`.", file=sys.stderr)
        return 2

    client = genai.Client(api_key=key)
    tickets = [
        json.loads(line)
        for line in SAMPLE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"Loaded {len(tickets)} tickets from {SAMPLE_PATH.name}\n")

    header = f"{'ID':<12} {'Category':<16} {'Present':<45} {'Missing':<30} {'Conf':<5}"
    print(header)
    print("-" * len(header))

    for i, ticket in enumerate(tickets, 1):
        raw = build_raw_ticket(ticket["entities"])
        print(f"[{i}/{len(tickets)}] {ticket['issue_id']} calling Gemini...", flush=True)
        parsed = classify_with_gemini(client, raw)
        if "error" in parsed:
            print(f"  ERROR: {parsed['error']}: {parsed['raw']}")
            continue
        present = ",".join(parsed.get("entities_present", []))[:44]
        missing = ",".join(parsed.get("entities_missing", []))[:29]
        row = (
            f"{ticket['issue_id']:<12} "
            f"{parsed.get('primary_category', '?'):<16} "
            f"{present:<45} "
            f"{missing:<30} "
            f"{parsed.get('confidence', 0):.2f}"
        )
        print(row)

    return 0


if __name__ == "__main__":
    sys.exit(main())
