# 0001 — Rule Book Format: Markdown Source, JSON Derived

## Status

Proposed, pending Arya + Yichen sign-off in this PR.

## Context

Yichen wrote the access-request triage spec as a markdown file
(`access_issue_state_machine.md`). It defines the state enums, event enums,
action enums, the entity schema, an abstract state shape, and one worked
example (ABP-1007).

Code — the rule book loader, the schema validators, and the downstream
agents — needs a machine-parseable representation of the same content.
Markdown is not directly loadable without writing a markdown parser, and
the loose embedded JSON snippets in the .md are illustrative, not normative.

## Decision

Keep the markdown file as the **human-editable source of truth**. Maintain a
derived JSON file (`ticket_triage/templates/access_request_v1.json`) that
restates the same content in machine-parseable form. Both live under
`ticket_triage/templates/`.

When the two disagree, the markdown wins. The JSON is the artifact that
gets corrected to match.

## Consequences

- Markdown stays the place humans edit when triage rules change.
- JSON is what `load_rulebook()` reads; it is validated against the enums
  in `ticket_triage.enums`, so drift between the JSON and the enums is
  caught at load time.
- The JSON is hand-edited to track the markdown for now. If drift becomes
  painful, a small generator script could derive JSON from the markdown —
  out of scope for this PR.
- Disagreement resolution: markdown wins; the JSON-side change is the one
  flagged in PR review.

## Alternatives Considered

- **JSON-only.** Rejected: markdown is what Yichen authored natively and
  what SMEs will review going forward.
- **YAML.** Rejected: not meaningfully more readable than JSON for this
  schema, and JSON already has first-class support in the standard library.
- **Embedded JSON inside the markdown file.** Rejected: mixing the human
  spec and the machine artifact in one file makes both harder to edit and
  diff.
