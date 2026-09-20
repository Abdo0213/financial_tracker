"""
schemas.py
----------
Public data contracts for the Transaction Extraction Agent.

Other developers integrating with this agent should import from here:

    from agents.extractor.schemas import TransactionType, Transaction, ExtractionResult
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, Enum):
    """
    The financial direction of a transaction.

    expense – Money paid out  (دفعت / اشتريت / صرفت …)
    income  – Money received  (قبضت / استلمت / مرتبي …)
    """

    EXPENSE = "expense"
    INCOME = "income"


class Transaction(BaseModel):
    """
    A single financial transaction extracted from an Arabic transcript.

    Fields
    ------
    amount : float
        The transaction amount. Must be greater than 0.
    currency : str
        ISO 4217 currency code. Defaults to "EGP" for Egyptian Pound.
    description : str
        The raw Arabic description of the item/service as spoken by the user.
        Must NOT be translated, categorized, or reworded.
    transaction_type : TransactionType
        "expense" or "income" inferred from context.

    Notes
    -----
    - The Categorization Agent will receive this object and assign a category.
      Do NOT pre-assign categories here.
    - description must preserve the original Arabic wording (e.g. "أوبر", "كتاب").
    """

    amount: float = Field(..., gt=0, description="Transaction amount, must be > 0.")
    currency: str = Field(
        default="EGP",
        min_length=1,
        description="ISO currency code. Defaults to EGP.",
    )
    description: str = Field(
        ...,
        min_length=1,
        description="Raw Arabic description of the item/service. No categories.",
    )
    transaction_type: TransactionType = Field(
        ..., description="'expense' or 'income' inferred from context."
    )

    @field_validator("currency")
    @classmethod
    def normalise_currency(cls, v: str) -> str:
        """
        Normalise common Arabic currency mentions to the ISO code.
        جنيه / جنيه مصري / EGP → EGP
        """
        mapping = {
            "جنيه": "EGP",
            "جنيه مصري": "EGP",
            "egp": "EGP",
            "le": "EGP",
            "جنيهات": "EGP",
        }
        return mapping.get(v.strip().lower(), v.strip().upper())

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        """Remove accidental leading/trailing whitespace."""
        return v.strip()


class ExtractionResult(BaseModel):
    """
    The structured output produced by the Transaction Extraction Agent.

    Fields
    ------
    transactions : List[Transaction]
        All financial transactions found in the transcript.
        Will be an empty list if no recognisable transactions are present —
        the agent must NOT invent transactions.

    Integration contract
    --------------------
    The Categorization Agent receives:

        extraction_result.transactions   →  List[Transaction]

    and adds a ``category`` field to each item.
    """

    transactions: List[Transaction] = Field(
        default_factory=list,
        description="List of extracted transactions. Empty if none found.",
    )

    @field_validator("transactions")
    @classmethod
    def validate_transactions_list(cls, v):
        """Ensure the value is a list (defensive guard)."""
        if not isinstance(v, list):
            raise ValueError("transactions must be a list.")
        return v
