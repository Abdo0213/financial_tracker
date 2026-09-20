"""
schemas.py
----------
Public data contracts for the Orchestrator Agent.

Other developers integrating with this agent should import from here:

    from agents.orchestrator.schemas import Intent, OrchestratorResult
"""

from enum import Enum
from pydantic import BaseModel, Field, field_validator


class Intent(str, Enum):
    """
    The set of intents the Orchestrator Agent can classify.

    ADD_TRANSACTION    – User wants to record a new income or expense.
    QUERY_TRANSACTIONS – User wants to retrieve / view existing transactions.
    UPDATE_TRANSACTION – User wants to correct / modify an existing transaction.
    DELETE_TRANSACTION – User wants to remove an existing transaction.
    UNKNOWN            – Intent could not be determined with sufficient confidence.
    """

    ADD_TRANSACTION = "ADD_TRANSACTION"
    QUERY_TRANSACTIONS = "QUERY_TRANSACTIONS"
    UPDATE_TRANSACTION = "UPDATE_TRANSACTION"
    DELETE_TRANSACTION = "DELETE_TRANSACTION"
    UNKNOWN = "UNKNOWN"


class OrchestratorResult(BaseModel):
    """
    The structured output produced by the Orchestrator Agent.

    Fields
    ------
    intent : Intent
        One of the five supported intents.
    confidence : float
        A score in [0.0, 1.0] representing the model's confidence in the
        classified intent. Values below 0.5 should be treated as low-confidence.
    reasoning : str
        A short, human-readable explanation (in English) of why the model
        chose this intent. Intended for debugging and logging only — the
        backend workflow must NOT rely on this field for logic.
    """

    intent: Intent = Field(..., description="Classified user intent.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )
    reasoning: str = Field(
        ...,
        description="Short explanation of why this intent was chosen.",
    )

    @field_validator("confidence")
    @classmethod
    def clamp_confidence(cls, v: float) -> float:
        """Ensure confidence is strictly within [0.0, 1.0]."""
        return max(0.0, min(1.0, float(v)))
