"""
agents/extractor/__init__.py
-----------------------------
Public re-exports for the Transaction Extraction Agent package.

Usage by the backend (or any other developer):

    from agents.extractor import ExtractionAgent, ExtractionResult, Transaction, TransactionType

    agent = ExtractionAgent()
    result = agent.extract_transactions("دفعت 120 جنيه أوبر")

    # result.transactions is what the Categorization Agent receives
    for tx in result.transactions:
        print(tx.amount, tx.description, tx.transaction_type)
"""

from .extractor import ExtractionAgent
from .schemas import ExtractionResult, Transaction, TransactionType

__all__ = [
    "ExtractionAgent",
    "ExtractionResult",
    "Transaction",
    "TransactionType",
]
