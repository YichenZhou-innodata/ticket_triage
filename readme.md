
**Project Background**

We are building an **automatic ticket triage agent** for an application support workflow.

In a system like ServiceNow, users file many different kinds of tickets:

- access requests
- application bugs
- report/download issues
- budget variance or data issues
- feature requests
- questions where the app is actually behaving as designed
- duplicate tickets

Today, a human support engineer reads each ticket, figures out what kind of issue it is, asks for missing information, routes it to the right team, marks duplicates, or drafts a reply.

The goal of this project is to build an **agentic triage framework** that can learn from historical tickets and assist humans with this process.

For v1, the system is a **copilot**, not a fully automatic ticket resolver. It recommends actions, but a human still reviews them.

---

**Status**

This repository is at **bootstrap stage**. The package layout described below is the *target* — most files do not exist yet. v1 is a copilot: every recommendation is human-reviewed before any real ticket action is taken.

---

**High-Level Architecture**

The project has two ADK agents:

1. **Ticket Executor Agent**

This agent handles one ticket at a time.

Its job is to:

- read the ticket
- extract useful fields
- classify the ticket
- detect missing information
- search for likely duplicates
- recommend the next action
- draft a human-reviewable comment

2. **Template Evolution Agent**

This agent looks at historical tickets.

Its job is to:

- inspect how tickets were handled in the past by human sme
- find repeated patterns
- suggest improvements to the rule book
- propose new categories, subcategories, required fields, or routing rules

It does **not** automatically rewrite the rule book yet. It only proposes changes for human SME review.

---

**Core Idea: State + Action + Rule Book**

The most important idea in this project is that ticket triage is modeled as a **state machine**.

For the `access_request` category, a clean request with all fields present and no duplicate takes the short happy path:

```text
new → intake → ready_for_access_review → approver_review
    → access_provisioning → verification → resolved
```

Other states are entered only when an event calls for them:

```text
from intake:   → missing_info       (required fields are missing)
               → duplicate_review   (a likely duplicate was found)
any time:      → stale_waiting_for_user, human_review
terminal:      resolved, closed, denied
```

So `missing_info` and `duplicate_review` are possible states a ticket may branch into, not required stops on the happy path.

Each state answers a specific question:

- `new` / `intake`: What information did the user provide, and what kind of ticket is this?
- `missing_info`: Are we missing required fields? (only if something is missing)
- `duplicate_review`: Does this look like an existing ticket? (only if a candidate was found)
- `ready_for_access_review` → `approver_review`: Is approval needed, and who approves?
- `access_provisioning` → `verification`: Has access been granted, and does it work?
- `human_review`: Should a human take over before any action is applied?

---

**The Rule Book**

The triage logic is authored by a human as a markdown spec and mirrored in a machine-readable JSON rule book that the code loads:

```text
access_issue_state_machine.md                    # human-authored source of truth
ticket_triage/templates/access_request_v1.json   # derived, machine-loadable rule book
```

Markdown is the source of truth; the JSON is kept in sync with it (see [ADR 0001](docs/decisions/0001-rulebook-format.md)).

Together they define the system's triage logic, containing:

- available states
- primary categories
- application issue subcategories
- required fields
- routing hints
- clarification prompts
- final review behavior

Think of them as the system's operating manual.

The code does not hard-code all decisions. Instead, it loads the rule book and uses it to decide what information is required and what action should be recommended.

---

**Example: Access Request**

If a user asks for access, the primary category is:

```text
access_request
```

The rule book says this category needs fields like:

- name
- employer id
- portfolio
- region
- user role
- project type
- leads
- additional context

If employer id is missing, the agent should not route the ticket yet.

Instead, it recommends an action like:

```text
Ask the reporter to provide the missing employer id.
```

So the state flow might look like:

```text
intake
→ classification: access_request
→ required_info_review: employer id missing
→ action_recommendation: ask_for_info
→ human_review
```

---

**Example: Application Issue**

Some tickets are application issues.

Primary category:

```text
application_issue
```

But application issues can have subcategories, such as:

```text
report_performance_issue
budget_variance_issue
data_quality_issue
ui_workflow_issue
integration_issue
```

For example, if a user says:

> I cannot download the performance report.

The agent may classify it as:

```text
primary_category = application_issue
subcategory = report_performance_issue
```

Then the rule book checks whether required fields are present:

- portfolio
- region
- site
- project code
- project name
- affected link
- screenshot
- detailed issue description

If those are present, the agent may recommend routing to:

```text
reporting-platform-support
```

---

**Actions**

Actions are the possible next steps the agent can recommend.

Examples:

```text
ask_for_info
route_to_team
suggest_duplicate_review
explain_intended_behavior
product_review
human_review
```

The important thing is that v1 actions are **recommendations**, not real ticket mutations.

The agent does not actually close a ticket, assign a ticket, or CC someone in ServiceNow.

It only says:

```text
Recommended action: route to reporting-platform-support.
Reason: report download issue with project code and affected link provided.
```

A human decides whether to apply it.

---

**Why State Machines Are Useful Here**

A state machine makes the agent easier to control.

Instead of asking an LLM to freely decide everything, we give it structure:

```text
Where is the ticket now?
What information is available?
What is missing?
What rule applies?
What action is allowed next?
```

This makes the system:

- easier to debug
- easier to test
- easier to evolve
- safer for production
- more understandable to human support teams

The intern should understand that the LLM is not the whole system. The LLM is part of a larger controlled workflow.

---

**Setup**

1. Clone the repository:

   ```text
   git clone https://github.com/YichenZhou-innodata/ticket_triage.git
   cd ticket_triage
   ```

2. Create and activate a Python virtual environment (Python 3.11+ recommended):

   ```text
   python -m venv .venv
   ```

   - PowerShell: `.\.venv\Scripts\Activate.ps1`
   - Bash / WSL / macOS: `source .venv/bin/activate`

3. Install dependencies:

   ```text
   pip install -r requirements.txt
   ```

   For running tests, also install dev dependencies:

   ```text
   pip install -r requirements-dev.txt
   ```

4. Configure the Google API key:

   ```text
   cp .env.example .env
   ```

   Then edit `.env` and set `GOOGLE_API_KEY` to a key from <https://aistudio.google.com/apikey>.

The Vertex AI path is also supported via `GOOGLE_GENAI_USE_VERTEXAI=TRUE` plus `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` and `gcloud auth application-default login`. The default (`FALSE`) uses the AI Studio Gemini Developer API.

---

**Project Structure**

```text
ticket_triage/
├── ticket_triage/
│   ├── __init__.py
│   ├── enums.py                       # State / Event / Action / Entity vocabulary
│   ├── schema.py                      # Pydantic models: TicketState, Entities, Approval, etc.
│   ├── rulebook.py                    # loads + validates rule book JSON files
│   ├── agent.py                       # ADK agent wiring (skeleton — built)
│   ├── domain/                        # classification / recommendation / evolution
│   │   ├── __init__.py
│   │   ├── classification.py          # (skeleton — built)
│   │   ├── recommendation.py          # (skeleton — built)
│   │   └── evolution.py               # (planned)
│   ├── templates/
│   │   └── access_request_v1.json     # machine-readable rule book (derived from spec)
│   └── data/
│       └── sample_tickets.jsonl       # 10 sample tickets covering 10 scenarios
├── tests/
│   ├── __init__.py
│   ├── test_schema.py
│   ├── test_rulebook.py
│   └── test_sample_tickets.py
├── docs/
│   └── decisions/
│       └── 0001-rulebook-format.md    # ADR: markdown source of truth, JSON derived
├── access_issue_state_machine.md      # Yichen's markdown spec (source of truth)
├── ARCHITECTURE.md                    # architecture, diagrams, open questions
├── readme.md
├── CONTRIBUTING.md
├── CLAUDE.md
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── .gitignore
```

---

**Where The Main Code Lives**

The important files are:

```text
ticket_triage/agent.py
```

Defines the two ADK agents:

- `ticket_executor_agent`
- `template_evolution_agent`

```text
ticket_triage/schema.py
```

Defines the data models: tickets, categories, entities, actions, templates, and outputs.

```text
ticket_triage/templates/access_request_v1.json
```

The rule book.

```text
ticket_triage/domain/classification.py
```

Classifies tickets into categories and subcategories.

```text
ticket_triage/domain/recommendation.py
```

Runs the state/action flow and recommends the next action.

```text
ticket_triage/domain/evolution.py
```

Looks at historical tickets and proposes improvements to the rule book.

```text
ticket_triage/data/sample_tickets.jsonl
```

Seed examples that simulate historical tickets.

---

**Documentation**

- [CONTRIBUTING.md](CONTRIBUTING.md) — branch naming, commit conventions, docstring requirements, PR process.
- [CLAUDE.md](CLAUDE.md) — guidance for AI assistants (Claude Code and similar) working in this repo.
- [ARCHITECTURE.md](ARCHITECTURE.md) — system overview, state-machine diagram, component diagram, and current open questions.

---

**One-Sentence Summary For The Intern**

This project is a ticket triage copilot that uses a state machine and a markdown rule book to classify tickets, check missing information, detect duplicates, recommend next actions, and gradually improve its own triage template from historical tickets.
