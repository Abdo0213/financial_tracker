"""
agents/orchestrator/__init__.py
--------------------------------
Public re-exports for the Orchestrator Agent package.

Usage by the backend (or any other developer):

    from agents.orchestrator import OrchestratorAgent, OrchestratorResult, Intent

    agent = OrchestratorAgent()
    result = agent.orchestrate("دفعت 120 جنيه أوبر")
    print(result.intent)       # Intent.ADD_TRANSACTION
    print(result.confidence)   # e.g. 0.97
    print(result.reasoning)    # e.g. "User stated they paid 120 pounds for Uber."
"""

from .orchestrator import OrchestratorAgent
from .schemas import Intent, OrchestratorResult

__all__ = [
    "OrchestratorAgent",
    "OrchestratorResult",
    "Intent",
]
