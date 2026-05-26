# Guidance for AI Assistants

This file is for AI coding assistants (Claude Code and similar) working in this repository. Read it before suggesting changes.

## Project Summary

This is a ticket triage copilot built on Google's Agent Development Kit (`google-adk`). It uses two ADK agents — a `ticket_executor_agent` that classifies one ticket at a time, checks for missing information, finds likely duplicates, and recommends a next action; and a `template_evolution_agent` that inspects historical tickets and *proposes* rule-book improvements. The agents are driven by a state machine and a markdown/JSON **rule book**, not by hard-coded logic. v1 is a **copilot** — it recommends, a human reviews and decides.

## Where To Read First

Read these, in order, before suggesting anything:

1. [readme.md](readme.md) — project background, architecture, state-machine design, rule-book concept, examples.
2. [CONTRIBUTING.md](CONTRIBUTING.md) — branch naming, commit conventions, docstring requirements, PR process.
3. `ticket_triage/templates/state_machine.v1.json` — the rule book (once it exists). This is the source of truth for categories, subcategories, required fields, and allowed actions.
4. `ticket_triage/schema.py` — the Pydantic models that define the contract between the rule book, the agents, and the rest of the code.
5. `ticket_triage/agent.py` — how the two ADK agents are wired up.

If a file you need is missing, the repo is still being scaffolded — check `git log` and recent branches to see what's in flight.

## Conventions To Follow

These are the rules in [CONTRIBUTING.md](CONTRIBUTING.md). Summary:

- **Branches:** `<owner>/<feature>` (e.g. `anand/classification-agent`). Never commit directly to `main`.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`). Body explains *why*, not what.
- **File header docstring:** Every Python file starts with a module docstring stating the file name and its purpose.
- **Function docstring:** Public functions document `Args:`, `Returns:`, `Raises:` in Google-style.
- **Inline comments:** Only where the *why* isn't obvious from the code. Skip comments that restate the code.
- **Type hints:** On all public function signatures.
- **PRs:** What / why / how-to-test. One review before merge.

## What To DO Before Suggesting Code

1. **Read the rule book.** If the change involves categories, subcategories, required fields, routing, or actions, the answer probably belongs in `ticket_triage/templates/state_machine.v1.json` — not in Python.
2. **Read `schema.py`.** It defines the data contract. Touching tickets, classifications, actions, or outputs means touching schemas.
3. **Check existing patterns.** If a similar function or agent already exists, mirror its style. Don't introduce a second way to do the same thing.
4. **Check for an in-progress branch.** Run `git branch -a` and `git log --all --oneline -20`. Another intern may already be working on what you're about to propose.

## What To NEVER Do

- **Never commit secrets.** No API keys, no `.env` contents in tracked files. `.env` is gitignored — keep it that way.
- **Never push directly to `main`.** All changes go through a PR from a `<owner>/<feature>` branch.
- **Never invent architecture decisions.** If the rule book doesn't list a category, agent, action, or required field, don't pretend it does. Propose the addition to a human first.
- **Never modify another intern's in-progress branch** without explicit coordination. Branches prefixed with someone else's name (`<teammate>/...`) are theirs.
- **Never bypass the human-review step in v1.** The agent recommends actions; it does not execute ticket mutations. Don't add code that closes, assigns, or comments on a real ticket without a human in the loop.
- **Never hard-code triage logic in Python that belongs in the rule book.** Categories, required fields, routing — those live in the JSON.
- **Never skip git hooks** (`--no-verify`) or bypass signing.
- **Never run destructive git operations** (`reset --hard`, `push --force`, `branch -D`) without explicit user approval.

## When To Ask The Human Instead Of Guessing

Stop and ask when the change touches any of these:

- **The rule book schema** (the shape of `state_machine.v1.json`, not just its contents). Schema changes ripple to `schema.py`, both agents, and any tests.
- **Agent prompts or system instructions.** Prompt changes affect model output quality and are hard to A/B test mid-PR. Get a human sign-off on the wording.
- **Public function signatures.** Renaming a parameter or changing a return type is a breaking change for everyone else's WIP code. Coordinate first.
- **Choice of model or API path** (Gemini Developer API vs. Vertex AI, model version, temperature). These are budget and compliance decisions, not engineering ones.
- **What counts as a "duplicate" ticket.** This is a product question, not a code question.
- **Adding a new top-level dependency.** Pin it, justify it in the PR, and check it doesn't conflict with the existing `requirements.txt`.

When in doubt: write up the question, leave the code untouched, and ask.
