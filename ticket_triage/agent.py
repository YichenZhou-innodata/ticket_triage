"""agent.py

Entry point for the ticket triage ADK agent. Wires up the LlmAgent
with Gemini and registers the classification and recommendation tools.
"""

from google.adk.agents import LlmAgent

from ticket_triage.domain.classification import classify_ticket
from ticket_triage.domain.recommendation import get_next_action

root_agent = LlmAgent(
    name="ticket_executor",
    model="gemini-2.0-flash",
    description="Triages IT support tickets.",
    instruction="""
        You are a ticket triage agent. When given a ticket:
        1. Classify it into a category using classify_ticket
        2. Check for missing required fields
        3. Recommend the next action using get_next_action
        
        Always return a structured response with the recommended action.
    """,
    tools=[classify_ticket, get_next_action],
)