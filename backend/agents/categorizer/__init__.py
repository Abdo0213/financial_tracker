"""
agents/categorizer/__init__.py
-------------------------------
Public re-exports for the Categorization Agent package.

Usage by the backend (or any other developer):

    from agents.categorizer import (
        CategorizationAgent,
        CategorizationResult,
        CategorizedTransaction,
        Category,
    )

    agent  = CategorizationAgent()
    result = agent.categorize_transactions(extraction_result.transactions)

    # result.transactions is what the database layer receives
    for tx in result.transactions:
        print(tx.description, tx.category)
"""

from .categorizer import CategorizationAgent
from .schemas import Category, CategorizedTransaction, CategorizationResult

__all__ = [
    "CategorizationAgent",
    "CategorizationResult",
    "CategorizedTransaction",
    "Category",
]
