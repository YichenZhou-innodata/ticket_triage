# Remaining Work Plan — Final Two Days

## Goal

Demo-solid by Friday. Not production-grade. The system needs to handle the
common demo paths without embarrassing behavior and without depending on
undocumented luck. Anything beyond that is out of scope for this plan.

## Method

Every item in this document has three steps in order: audit, propose,
implement + verify. Never skip the audit; the code state today is not
always what you assume from earlier docs or memory.

## Rule of last resort

If this document contradicts what you find in the code, **trust the code**
and update this document as part of your change. This plan was written on
a specific `main` tip and the codebase moves.

---

## Current state (verified on `main` at commit `3fc474d`)

Snapshot from a Stage 0 audit run against a clean checkout. If your `git
log` shows a later main, redo the audit before believing this section.

### What works, verified

- **Schema + rule-book loader + JSONL loader** — validation layer is
  strict, length-bounded, and rejects bad input with clear messages.
  ([`ticket_triage/schema.py`](ticket_triage/schema.py),
  [`ticket_triage/rulebook.py`](ticket_triage/rulebook.py),
  [`ticket_triage/sample_tickets.py`](ticket_triage/sample_tickets.py))
- **Rule book loaded at import time** in
  [`ticket_triage/agent.py`](ticket_triage/agent.py) and the concrete
  state/action/event lists are injected into the LlmAgent instruction so
  the model reasons with real facts rather than fabricating a partial
  rulebook.
- **Human-review invariant enforced** at the tool boundary:
  `ticket_state.requires_human_review = True` is set unconditionally in
  `get_next_action` ([`recommendation.py:40`](ticket_triage/domain/recommendation.py#L40)).
  Caveat: the model composes its user-visible summary from its own
  constructed state, so the rendered output may still show whatever the
  model decided. The invariant holds on the state object, not necessarily
  in the summary.
- **Audit trail populated per invocation** — every `get_next_action`
  call appends one `AuditEntry` recording the cascade branch that fired,
  the input state, and the resulting action
  ([`recommendation.py:71-82`](ticket_triage/domain/recommendation.py#L71-L82)).
  Rows use `from_state == to_state` and are marked
  "recommendation decision (not a state transition)" so they aren't
  mistaken for real transitions.
- **Model string** — `gemini-flash-latest`
  ([`agent.py`](ticket_triage/agent.py) — search for `model=`). Working
  free-tier quota confirmed by multiple live invocations.
- **Test suite** — `pytest tests/ -v` → **61 passed, 6 xfailed**, zero
  errors.

### What does not work / is a stub / has known gaps

- **`classify_ticket` is a hardcoded stub.**
  [`ticket_triage/domain/classification.py:12-26`](ticket_triage/domain/classification.py#L12-L26).
  The function takes `ticket_text: str` and `rulebook: Rulebook` but the
  body ignores both. Every call returns `PrimaryCategory.ACCESS_REQUEST`
  regardless of content. Live-verified: a bug report ("I found a bug in
  the report generator") comes back classified as `access_request` and
  the reporter is asked for their `employee_id`.
- **`PrimaryCategory` has exactly one member.**
  [`ticket_triage/enums.py:107-116`](ticket_triage/enums.py#L107-L116) —
  only `ACCESS_REQUEST = "access_request"`. Structurally impossible for
  the system to say "this is not an access request" today.
- **Cascade handles 1 of 13 states explicitly.**
  [`recommendation.py`](ticket_triage/domain/recommendation.py) has
  content checks for `missing_fields` (line 42) and
  `duplicate_candidates` (line 48), then one state check for
  `state == State.INTAKE` (line 54), then a fallthrough to
  `escalate_to_human` (line 60-65). Twelve of thirteen states hit the
  fallthrough unless a content check short-circuits earlier.
- **Six xfails document the specific cascade gaps.**
  [`tests/test_recommendation.py`](tests/test_recommendation.py).
  Grouped by root cause:
  - State-blind cascade (3 tests): `test_sample_001_ready_for_access_review`,
    `test_sample_006_access_provisioning`, `test_sample_007_denied` —
    "no branch for X; falls through to escalate_to_human"
  - Ordering bug — content checked before state (2 tests):
    `test_sample_008_stale_waiting_for_user`,
    `test_sample_010_human_review` — "missing_fields checked before
    state, so [terminal state] with lingering missing_fields returns
    ask_for_missing_info instead of [correct action]"
  - Fresh-vs-reopened blindness (1 test): `test_sample_009_reopened_intake` —
    "cascade cannot distinguish fresh intake from reopened intake;
    returns request_approval instead of extract_fields for reopened
    tickets"
- **Zero error handling in the agent module.**
  `grep "try:\|except" ticket_triage/agent.py` returns nothing. Runtime
  Gemini failures (rate limits, network) propagate raw as stack traces.
  (See nuance in Part 2.3 — the module-level `load_rulebook` at import
  is a *deliberate* fail-fast, not a gap.)
- **Rule book vs cascade — the semantic conflict on `intake`.**
  Rule book: `allowed_actions_per_state["intake"] = ['extract_fields',
  'suggest_duplicate_review']`. Cascade: returns
  `RecommendedActionType.REQUEST_APPROVAL` when `state == INTAKE`
  ([`recommendation.py:57`](ticket_triage/domain/recommendation.py#L57)).
  `request_approval` is listed only under `ready_for_access_review` in
  the rule book. This is the blocker for a data-driven rewrite.

### Test baseline

```
$ pytest tests/ -v
...
61 passed, 6 xfailed
```

Any change should preserve this baseline. The six xfails are expected;
they are the acceptance criteria for the cascade work in Part 2.2. When
the cascade is made state-aware, they should flip to XPASS naturally —
not by weakening the assertions.

---

## KNOWN TRAP — READ BEFORE TOUCHING THE CASCADE

**The happy path works because two bugs cancel each other out.**

1. The cascade in `get_next_action` only handles `state == intake` with
   an explicit positive branch. Everything else falls through to
   `escalate_to_human`.
2. The model, when triaging a ticket, tends to default to
   `state=intake` for anything it isn't sure about. This lazy default
   masks bug #1 — the cascade's intake branch fires and the demo
   appears to work.

Fixing one side in isolation breaks the demo. A prompt nudge toward
more accurate state selection was tested and **deliberately withheld**
during the rule-book-injection work; more accurate state selection
would shift happy-path tickets from `intake` to
`ready_for_access_review`, at which point the cascade's intake branch
no longer fires and the happy path regresses to `escalate_to_human`.

**Full analysis + the fix path lives in the `NOTE` block in
[`ticket_triage/agent.py`](ticket_triage/agent.py)** — search for
`# NOTE — TWO BUGS CANCELLING OUT`. Read it before starting Part 2.
That NOTE is the map for the intake-vs-request_approval semantic
disagreement between the rule book and the cascade.

---

## Working method — every item follows this

1. **AUDIT.** Read the code the item touches. Confirm current behavior
   with concrete evidence — file:line references, a `pytest` run, or a
   short script that demonstrates the actual behavior. Write down what
   you found before proposing any change. If the audit contradicts this
   document, the audit wins.
2. **PROPOSE.** State the change concretely. Name the file(s) and
   function(s) you'll touch. Say what could break, and how you'll
   verify the change (unit test, live call, both). Get sign-off before
   implementing anything with live-call verification (quota is
   shared — see Coordination).
3. **IMPLEMENT + VERIFY.** Make the change on a small, independently
   revertable branch. Run the full suite. If the item affects live
   agent behavior, do the live verification you proposed. Do not push
   unverified work.

If a step surprises you (audit contradicts expectation, verify shows
regression, a test fails you didn't anticipate) — stop and report
before continuing. The demo is fragile; recovery is easier than
diagnosis-after-the-fact.

---

## Part 1 — Classification and Safe Output

**Owner: Part 1 owner.**

**Files this part is allowed to touch:**
- [`ticket_triage/domain/classification.py`](ticket_triage/domain/classification.py)
- [`ticket_triage/enums.py`](ticket_triage/enums.py) (adding to
  `PrimaryCategory` only)
- [`ticket_triage/agent.py`](ticket_triage/agent.py) (instruction
  updates only, not tool wiring or model string)
- [`ticket_triage/schema.py`](ticket_triage/schema.py) (only if a new
  category requires a schema addition)
- Any file under [`tests/`](tests/)

**Do NOT touch:** anything under
[`ticket_triage/domain/recommendation.py`](ticket_triage/domain/recommendation.py),
the rule book JSON, or the model string.

### 1.1 Make classification real

**Problem.** Every ticket returns `access_request` regardless of
content. The stub is at
[`classification.py:26`](ticket_triage/domain/classification.py#L26).
Live-verified: a bug report gets asked for an employee ID. This is
audit finding F1.

**Approach.** Add an `UNKNOWN` (or `OTHER` — Part 1 owner's call, but
pick one and document it) member to `PrimaryCategory`. Replace the
hardcoded return in `classify_ticket` with a real implementation.
Prefer a rule-based keyword classifier over an LLM call because:
- Deterministic — testable in the unit-test suite with no quota.
- Predictable in a demo — no surprise LLM outputs.
- Cheap — no round-trip cost.

A minimal starting set of keywords for `access_request` might be
`{"access", "permission", "role", "portfolio", "workbook", "dashboard"}`;
anything that doesn't match returns the new `UNKNOWN` category. Refine
against the 10 sample tickets in
[`ticket_triage/data/sample_tickets.jsonl`](ticket_triage/data/sample_tickets.jsonl)
so all 10 land on `access_request`.

**Verify.**
- Add unit tests in `tests/test_classification.py` (new file — this
  layer currently has zero test coverage) covering: at least one
  positive case per keyword, an obvious bug-report case that returns
  `UNKNOWN`, gibberish returns `UNKNOWN`, empty string returns
  `UNKNOWN`.
- Full suite green (baseline: 61/6xfail; new tests add to the 61).
- **One live call** with the same "bug in the report generator" text
  used in the audit. Must NOT ask for `employee_id`.

### 1.2 Handle the unknown path end-to-end

**Problem.** Adding a new category is only half. The agent needs a
code path for it — otherwise the LLM will call `classify_ticket`, see
`UNKNOWN`, and improvise.

**Approach.** Two edits, both in
[`ticket_triage/agent.py`](ticket_triage/agent.py):
- Update the composed instruction (in `_compose_instruction`) so it
  explicitly tells the model: if `classify_ticket` returns `UNKNOWN`,
  do not call `get_next_action`; return an escalation message like
  "This ticket does not appear to be an access request; routing to a
  human." Keep the flag `requires_human_review = True` in the response.
- Do not add a new tool. The classification tool's return already
  carries the signal — a wrapper tool would add complexity without
  buying anything.

**Verify.**
- Unit tests for the instruction composition — deterministic string
  content assertions.
- **One live call** with a non-access ticket. The response must escalate
  to human review with a clear reason. Must not invoke `get_next_action`.

### 1.3 Edge-case hardening on input

**Audit finding — MOSTLY COVERED BY 1.1 + 1.2.**

The 1.3 audit found that the meaningful input gaps were closed by the
prior two items:

- **Empty and whitespace-only input** — handled by
  [`classify_ticket`](ticket_triage/domain/classification.py) line 134:
  `if not ticket_text or not ticket_text.strip(): return
  PrimaryCategory.OTHER`. Combined with 1.2's OTHER short-circuit
  (instruction + code guard), empty/whitespace tickets escalate to
  human without crashing and without asking a bug reporter for an
  employee_id. Two dedicated tests pass today.
- **Very short and content-free input** (`"hi"`, `"asdf"`, `"!!!"`,
  `"12345"`) — passes the empty check, matches no keyword, returns
  OTHER → escalates. Same code path as above.
- **Non-English input** — the keyword set is English-only,
  deliberately. Spanish / French / Chinese / Arabic tickets match no
  keyword and route to OTHER → escalate to human. **This is correct
  behavior for v1, not a gap.** Adding translated keywords would
  narrow the escalation guard's coverage without solving the
  extraction problem: the entire downstream pipeline (entity
  prompts, required field names, approval workflow) is
  English-centric. See the "Non-English input" section of
  [`classification.py`](ticket_triage/domain/classification.py)'s
  module docstring for the full analysis.

**Scope decision — no Python-side length cap on `ticket_text`.**

A tempting addition is a `max_length` check on `classify_ticket`'s
`ticket_text` argument. **This does not do what a reader would think
it does.** The classifier is a TOOL called BY the model, so the
ticket text has already been sent to Gemini as user content by the
time `classify_ticket` runs. The costs (tokens spent on the model
call, latency, potential rejection by Gemini's own token limits) have
already been incurred. Adding a Python-side cap here would give a
reader false confidence that oversized inputs are being turned away
at the door. A meaningful size guard would need to live in caller
code before `Runner.run()`, which is out of scope for v1 (human-driven
demo, no public webhook, realistic ticket sizes well under 10K
chars). Documented instead of implemented.

**Residual scope actually implemented in 1.3:**

- Regression tests in
  [`tests/test_classification.py`](tests/test_classification.py) that
  pin current behavior for input classes not previously covered:
  non-English (Spanish, French, Chinese, Arabic), mixed-language,
  short-content edge cases (single word, punctuation-only,
  digits-only), and a very-long-input smoke test that verifies the
  regex handles ~120k characters without crashing.
- A "Non-English input" section added to
  [`classification.py`](ticket_triage/domain/classification.py)'s
  module docstring explaining why non-English tickets deliberately
  escalate and why adding translated keywords is not the right fix.
- A "Residual failure mode" note on the OTHER-guard test section in
  [`tests/test_recommendation.py`](tests/test_recommendation.py)
  recording the LLM-compliance risk: the guard fires on the
  TicketState's `primary_category` field, so if the model ignores
  `classify_ticket`'s OTHER return and constructs a TicketState with
  `primary_category=ACCESS_REQUEST` anyway, the guard does not fire.
  Not fixable at the code layer; noted so it isn't forgotten.

**Verify.** Unit tests only. Zero live-call cost.

**Note on required vs provisional fields — READ BEFORE HARDENING.**
The rule book distinguishes:
- `required_fields = ['employee_id']` — spec-confirmed, one field.
- `provisional_required_fields = ['name', 'portfolio', 'region',
  'user_role', 'project_type', 'leads', 'additional_context']` —
  inferred from the entity schema, pending sign-off.

**Neither the cascade nor `classify_ticket` distinguishes these
today.** Anyone doing input hardening should *not* start enforcing
the provisional set as if it were required. That's an unresolved spec
question, not a gap for this item to fill. If a test looks like it's
enforcing more than `['employee_id']`, question the test.

---

## Part 2 — Recommendation and Reliability

**Owner: Part 2 owner.**

**Files this part is allowed to touch:**
- [`ticket_triage/domain/recommendation.py`](ticket_triage/domain/recommendation.py)
- [`ticket_triage/templates/access_request_v1.json`](ticket_triage/templates/access_request_v1.json)
  (only for 2.1's rationale-driven changes, and only after 2.1's audit
  is complete)
- [`ticket_triage/agent.py`](ticket_triage/agent.py) (only for the
  error-handling changes in 2.3; do not touch the instruction or
  model)
- Any file under [`tests/`](tests/)

**Do NOT touch:** anything under
[`ticket_triage/domain/classification.py`](ticket_triage/domain/classification.py)
or [`ticket_triage/enums.py`](ticket_triage/enums.py) — those are
Part 1's responsibility.

### 2.1 Resolve the state semantic conflict — **DO THIS FIRST, IT BLOCKS 2.2**

**Problem.** The rule book and the cascade disagree about what
`state=intake` permits, and by extension about which state should
trigger `request_approval`. See the KNOWN TRAP section above and the
`NOTE` block in `agent.py` for the full analysis.

**Approach.**
1. Build a state-by-state comparison table. Rows: all 13 members of
   `State` (from
   [`enums.py`](ticket_triage/enums.py) — search for `class State`).
   Columns: what
   `access_request_v1.json`'s `allowed_actions_per_state` permits vs.
   what `get_next_action` actually returns for that state (given
   representative content). This table is the deliverable of the
   audit step for 2.1.
2. Identify every state where the two disagree. There is at least one
   confirmed: `intake`. There may be more — the sample-ticket ground
   truth expects `send_follow_up_reminder` for
   `stale_waiting_for_user`, but the cascade returns
   `ask_for_missing_info` when there are lingering `missing_fields`,
   which is a different flavor of disagreement (see xfail
   `test_sample_008_stale_waiting_for_user`).
3. For each disagreement, decide one of three:
   - **Amend the rule book** — if the cascade's behavior is right for
     the demo and the rule book was wrong.
   - **Amend the cascade** — if the rule book is right and the
     cascade should conform.
   - **Add a mapping layer** — if neither is entirely right and a
     helper is needed to translate state to action deterministically.
4. Write a short rationale for each decision (not just a code
   change). File it as a comment in the rule book JSON's `notes`
   block or as an ADR under [`docs/decisions/`](docs/decisions/).

**Note on `todo_transitions` — CHECK THESE FIRST.** The rule book has
**8 open entries** in its `todo_transitions` list. Some of the state
disagreements identified in step 2 above may be resolvable by
**promoting** a `todo_transitions` entry to a real transition rather
than inventing something new. Read
[`access_request_v1.json`](ticket_triage/templates/access_request_v1.json)
— search for `todo_transitions` — before proposing any addition. If
a `todo_transitions` entry matches what you need, promote it (with a
rationale).

**Verify.**
- Full suite green (baseline: 61/6xfail).
- **One live call** with the standard happy-path ticket. The
  recommendation must be `request_approval` (same as today).
- Table + rationale committed alongside the code change.

### 2.2 Make the cascade state-aware

**Problem.** One of 13 states is handled explicitly. Six xfail tests
in [`tests/test_recommendation.py`](tests/test_recommendation.py)
document the specific gaps (see the audit findings above for the
three root-cause groupings).

**Approach.** Prerequisite: 2.1 is landed and the semantic
disagreements are resolved. Then:
- Evaluate state **before** content in
  [`recommendation.py`](ticket_triage/domain/recommendation.py).
  Terminal states (`resolved`, `closed`, `denied`,
  `stale_waiting_for_user`, `human_review`) should not be overridden
  by lingering `missing_fields` (this is the ordering bug from xfails
  008 and 010).
- For non-terminal states without missing_fields / duplicates,
  consult `rulebook.allowed_actions_per_state[state]` and select the
  first allowed action (or a more sophisticated rule if the audit
  suggests one). This is what makes the cascade data-driven.
- Keep the content checks (`missing_fields`, `duplicate_candidates`)
  but subordinate them to state — content overrides only when the
  state allows the content-based action.
- Handle fresh-vs-reopened `intake` (xfail 009) — check
  `last_event == Event.TICKET_REOPENED` or scan `audit` for a prior
  `ticket_reopened` entry.
- Preserve the audit-trail append and `requires_human_review = True`
  mutation added in PR #10 — do not regress those.

**Verify.**
- The six xfail tests should begin **passing on their own**. Do NOT
  weaken any assertion in `tests/test_recommendation.py` to force
  them through. If an xfail flips because your change is right, great.
  If it flips because the assertion no longer means what it did, that
  is a regression in the tests.
- Full suite green.
- **One live call** to confirm the happy path is still intact.

### 2.3 Error handling on the agent path

**Problem.** No `try`/`except` anywhere in
[`ticket_triage/agent.py`](ticket_triage/agent.py). Rate limits and
model errors propagate as raw stack traces. Live-observed: `429
RESOURCE_EXHAUSTED` blew up mid-run during the earlier audit.

**Approach.**
- Wrap the invocation path (wherever the agent-orchestrated Gemini
  call happens) with a targeted `try` / `except` on the specific
  exception classes actually observed:
  `google.genai.errors.ClientError` (which carries the HTTP status;
  filter on 429 / 5xx) and any transport-layer network errors.
- Return a clear degraded response for each caught class — for 429,
  something like "Service is temporarily rate-limited; the request
  has been queued for human review." For other model errors,
  "Automated triage is unavailable; escalating to human review."
- **No bare `except:`**. Name the exception classes.
- Keep the `requires_human_review = True` flag on any degraded
  response.

**Verify.** Unit tests with mocked failures (patch
`google.genai.Client.models.generate_content` to raise the specific
exceptions). No live quota needed.

**Nuance — DO NOT REMOVE.** The module-level
`_RULEBOOK: Rulebook = load_rulebook(_RULEBOOK_PATH)` in `agent.py`
raises `RulebookLoadError` at import time if the JSON is missing or
corrupt. That is **intentional fail-fast** and should stay uncaught —
an agent that silently ignores its rule book is worse than one that
refuses to start. This item is only about runtime model errors (rate
limiting, network), not about import-time errors.

---

## Coordination

- **Contract boundary.** Part 1 owns classification and the category
  enum. Part 2 owns the recommendation path, the rule book, and error
  handling. The **shared surface** is the state model
  (`State` enum + `TicketState` schema). If either part needs to
  change the state model, agree with the other owner first.
- **Sequencing.** Part 1 and Part 2 are independent and parallel. Within
  Part 2, **2.1 must land before 2.2** — the cascade cannot be made
  data-driven while the rule book and cascade disagree about intake.
- **Branching.** One branch per item, small and independently
  revertable. Merge each item on its own PR so the demo can be rolled
  back to the last known-good state at any point. Avoid stacking
  branches unless one item genuinely blocks another.
- **Quota.** Live verification is shared and limited (free-tier Gemini
  quota is per-day and finite). **Coordinate before spending calls.**
  Items verifiable with unit tests alone — 1.3 and 2.3 — are the ones
  to do when quota is gone.
- **Documented incomplete beats unverified branch.** If an item can't
  be finished by Friday, commit what's verified with a `# TODO`
  comment that names the incomplete piece, and update this document
  to reflect what remains. A documented incomplete item is a handoff.
  An unverified branch is a hidden landmine.

---

## Out of scope — recorded so nobody rediscovers these

These are known gaps. They are **not** in the two-day plan. If any of
them turn out to be blockers for the demo, escalate rather than
attempting them under time pressure.

- **Duplicate detection.** Not implemented. The
  `duplicate_candidates` field exists on `TicketState` but no code
  populates it. Implementing duplicate detection needs a similarity
  approach (embedding? keyword? fuzzy match?), a threshold decision,
  and a plan for comparison cost at scale. None of that fits in two
  days without cutting corners.
- **The evolution agent.** Not started. Referenced in the readme and
  ARCHITECTURE.md, no code exists. Structure of "proposed rule-book
  updates" would need to be defined before implementation.
- **Ground truth authority.** Test expectations encode one person's
  assumptions about what each sample ticket should trigger. Real
  correctness measurement needs an SME-labelled corpus. There is no
  such corpus today.
- **Production observability.** No `logging` calls anywhere in the
  code (`grep "^import logging\|^from logging" ticket_triage/`
  returns nothing). No metrics, no correlation IDs, no request tracing.
  The `audit` trail added in PR #10 lives on the per-invocation
  `TicketState` object; it's not surfaced to any external observer.
- **Volume / latency / cost targets.** Undefined. There is no
  documented request rate, no acceptable latency, no monthly cost
  ceiling. Any change made for "scale" is unmeasured against absent
  targets.
- **Multi-category tickets.** The schema permits exactly one
  `primary_category` per ticket
  ([`schema.py`](ticket_triage/schema.py) — `primary_category` field).
  Whether a ticket should be able to be classified into multiple
  categories at once is undecided.

---

## Handoff reading order

Read these five, in this order, before touching anything:

1. **[`ARCHITECTURE.md`](ARCHITECTURE.md)** at the repo root. Whole
   system view. The Mermaid state-machine diagram is the map.
2. **The `NOTE` block in
   [`ticket_triage/agent.py`](ticket_triage/agent.py)** (search for
   `# NOTE — TWO BUGS CANCELLING OUT`). Do not skip this. It is the
   reason the demo works and the reason a naive fix breaks it.
3. **The six xfail tests in
   [`tests/test_recommendation.py`](tests/test_recommendation.py)**.
   Each xfail's `reason=` string names the specific cascade gap it
   pins. These are the acceptance criteria for Part 2.2.
4. **The rule book's `notes` and `todo_transitions` blocks in
   [`ticket_triage/templates/access_request_v1.json`](ticket_triage/templates/access_request_v1.json)**.
   The `todo_transitions` list is directly relevant to Part 2.1 —
   promote from it rather than inventing.
5. **This document.**

---

The happy path works for reasons that are not correctness. **Verify
current behavior before assuming an improvement is safe.**
