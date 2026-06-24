"""agent.py

Entry point for the ticket triage ADK agent. Wires the LlmAgent
with Gemini and registers the classification and recommendation tools.
"""

from google.adk.agents import LlmAgent

root_agent = LlmAgent(
    name="ticket_executor",
    model="gemini-2.0-flash",
    description="Triages support tickets.",
    instruction="""
        You are a ticket triage agent. When given a ticket:
        1. Classify it into a category
        2. Check for missing required fields
        3. Recommend the next action
    """,
)