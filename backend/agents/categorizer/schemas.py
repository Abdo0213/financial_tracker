"""
schemas.py
----------
Public data contracts for the Categorization Agent.

Other developers integrating with this agent should import from here:

    from agents.categorizer.schemas import (
        Category,
        CategorizedTransaction,
        CategorizationResult,
    )

The Categorization Agent receives a list of Transaction objects from the
Transaction Extraction Agent and returns a CategorizationResult whose
transactions have exactly one extra field: ``category``.
"""

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator

# Re-export upstream types so callers only need one import path
from agents.extractor.schemas import Transaction, TransactionType  # noqa: F401


class Category(str, Enum):
    """
    The fixed set of categories the Categorization Agent may assign.

    food           – Groceries, restaurants, cafes, food delivery
    transportation – Uber, taxis, fuel, metro, bus
    shopping       – Clothes, accessories, general retail
    education      – Books, courses, tuition, school fees
    healthcare     – Pharmacies, doctors, hospitals, labs
    entertainment  – Cinema, streaming, games, sports
    bills          – Utilities: electricity, water, gas, internet, phone
    housing        – Rent, mortgage, maintenance
    income         – Salary, freelance pay, transfers received
    other          – Anything that doesn't fit the above categories
    """

    FOOD           = "food"
    TRANSPORTATION = "transportation"
    SHOPPING       = "shopping"
    EDUCATION      = "education"
    HEALTHCARE     = "healthcare"
    ENTERTAINMENT  = "entertainment"
    BILLS          = "bills"
    HOUSING        = "housing"
    INCOME         = "income"
    OTHER          = "other"


class CategorizedTransaction(BaseModel):
    """
    A Transaction enriched with exactly one category.

    All original fields from Transaction are preserved unchanged.
    Only ``category`` is added by the Categorization Agent.

    Fields
    ------
    amount : float
        Original amount — must NOT be modified.
    currency : str
        Original currency — must NOT be modified.
    description : str
        Original Arabic description — must NOT be modified.
    transaction_type : TransactionType
        Original type ("expense" / "income") — must NOT be modified.
    category : Category
        The single standardized category assigned by the agent.
    """

    amount: float = Field(..., gt=0, description="Original transaction amount.")
    currency: str = Field(..., min_length=1, description="Original ISO currency code.")
    description: str = Field(..., min_length=1, description="Original Arabic description.")
    transaction_type: TransactionType = Field(
        ..., description="Original transaction type."
    )
    category: Category = Field(
        ..., description="Standardized category assigned by the Categorization Agent."
    )

    @field_validator("description")
    @classmethod
    def strip_description(cls, v: str) -> str:
        return v.strip()


class CategorizationResult(BaseModel):
    """
    The structured output produced by the Categorization Agent.

    Fields
    ------
    transactions : List[CategorizedTransaction]
        All transactions with their assigned categories.
        The count MUST equal the count of the input Transaction list.

    Integration contract
    --------------------
    The backend database layer receives:

        categorization_result.transactions   →  List[CategorizedTransaction]

    and persists each item to the database.
    """

    transactions: List[CategorizedTransaction] = Field(
        default_factory=list,
        description="Categorized transactions. Count must match input count.",
    )

    @field_validator("transactions")
    @classmethod
    def must_be_list(cls, v) -> list:
        """Ensure the value is a list (defensive guard)."""
        if not isinstance(v, list):
            raise ValueError("transactions must be a list.")
        return v
