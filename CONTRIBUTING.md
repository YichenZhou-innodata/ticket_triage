# Contributing

This document describes how we collaborate on the ticket triage project. It applies to everyone working on the repo (interns and reviewers).

## Workflow: Trunk-Based, PR-Only

We use a trunk-based workflow with `main` as the trunk.

- **No direct commits to `main`.** Ever. All changes land via pull request.
- `main` should always be in a working, runnable state.
- Keep branches short-lived. Merge or close them within a few days; don't let them rot.
- Rebase onto the latest `main` before opening a PR to keep history linear.
- Squash-merge PRs unless there's a specific reason to preserve individual commits.

## Branch Naming

Use a personal namespace prefix, then a short kebab-case description of the feature.

```
<owner>/<feature>
```

Examples:

- `anand/setup`
- `anand/classification-agent`
- `<teammate>/schema-models`
- `<teammate>/rulebook-loader`

Use `fix/` or `chore/` as the second segment for non-feature work if it helps:

- `anand/fix/duplicate-detection-edge-case`
- `<teammate>/chore/bump-google-adk`

## Commit Messages: Conventional Commits

Follow the [Conventional Commits](https://www.conventionalcommits.org/) spec.

Format:

```
<type>(<optional scope>): <short summary>

<optional body explaining the why>

<optional footer, e.g. BREAKING CHANGE: ...>
```

Allowed types:

- `feat` — a new feature or capability
- `fix` — a bug fix
- `docs` — documentation only
- `refactor` — code change that neither fixes a bug nor adds a feature
- `test` — adding or correcting tests
- `chore` — build, tooling, dependencies, repo housekeeping
- `perf` — performance improvement

Examples:

```
feat(classification): add subcategory inference for application_issue
fix(duplicate-check): handle empty embeddings list
docs(readme): clarify rule book location
chore(deps): pin google-adk to 2.1.0
```

Keep the summary under ~72 characters. Use the body to explain **why**, not what (the diff already shows what).

## Code Style

### File Header Docstring (required)

Every Python source file starts with a module-level docstring stating the **file name and its purpose**.

```python
"""classification.py

Classifies a ticket into a primary category and (where applicable) a subcategory
using the rule book and the LLM-backed classification agent.
"""
```

### Function Docstring (required)

Every public function and method has a docstring documenting **args, returns, and raises**. Use Google-style docstrings to match the Google SDK ecosystem.

```python
def classify_ticket(ticket: Ticket, rulebook: RuleBook) -> Classification:
    """Classify a single ticket against the active rule book.

    Args:
        ticket: The incoming ticket to classify.
        rulebook: The loaded rule book defining categories and required fields.

    Returns:
        A Classification with primary_category, optional subcategory, and confidence.

    Raises:
        RuleBookError: If the rule book is missing a required category definition.
    """
```

Private helpers (`_name`) can use a one-line docstring if the signature is self-evident.

### Inline Comments

Comments explain **why**, not what. Skip the comment if a reader who knows Python can answer "why is this here?" from the code alone.

Good — non-obvious constraint:

```python
# ADK's Runner requires session_service to be created before the agent runs;
# constructing it lazily inside run() causes a race in async tests.
session_service = InMemorySessionService()
```

Bad — restates the code:

```python
# Increment counter by 1
counter += 1
```

### General

- Type hints on all public function signatures.
- Keep functions small. If a function needs scrolling to read, it probably needs splitting.
- Don't introduce abstractions until there are two real call sites.

## Pull Requests

PR description should include:

1. **What** changed — one or two sentences.
2. **Why** — link to the README section, ticket, or design discussion if relevant.
3. **How to test** — commands or steps a reviewer can run.

Request review from at least one other contributor before merging. Don't merge your own PR unless explicitly approved.

## Local Setup

1. Create a venv: `python -m venv .venv`
2. Activate: `.venv\Scripts\Activate.ps1` (PowerShell) or `source .venv/bin/activate` (bash)
3. Install: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env` and set `GOOGLE_API_KEY` (see the project [readme.md](readme.md) Setup section).

## What Not to Commit

- `.venv/`, `__pycache__/`, `.pytest_cache/`
- `.env` files containing real credentials
- IDE-specific config (`.vscode/`, `.idea/`) unless we agree to share it
- Generated artifacts (logs, model caches)

Use `.gitignore` to enforce these; don't rely on memory.
