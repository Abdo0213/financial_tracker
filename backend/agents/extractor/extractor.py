"""
extractor.py
------------
Core implementation of the Transaction Extraction Agent.

Public interface (called by the backend workflow after the Orchestrator):

    from agents.extractor.extractor import ExtractionAgent

    agent = ExtractionAgent()
    result = agent.extract_transactions(transcript)   # -> ExtractionResult

The agent receives an Arabic transcript and extracts all financial
transactions as structured data.  It does NOT categorize, does NOT
access the database, and does NOT perform any downstream logic.

Configuration is read from the same .env as the Orchestrator:

    OLLAMA_API_KEY   – API key for the LLM provider
    OLLAMA_BASE_URL  – OpenAI-compatible base URL  (default: https://ollama.com/v1)
    OLLAMA_MODEL     – Model name                   (default: gpt-oss:120b)
"""

import json
import logging
import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from .schemas import ExtractionResult, Transaction, TransactionType

# Load .env from project root (three levels up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

_DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
_DEFAULT_MODEL    = os.getenv("OLLAMA_MODEL",    "gpt-oss:120b")
_DEFAULT_API_KEY  = os.getenv("OLLAMA_API_KEY",  os.getenv("OPENAI_API_KEY", ""))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Transaction Extraction Agent for an Arabic personal finance tracker.
Your ONLY job is to extract financial transactions from a speech-to-text transcript.

You understand both Egyptian Colloquial Arabic (عامية مصرية) and Modern Standard Arabic (فصحى).

## Number formats you must handle
- Western numerals:   120, 350, 15000
- Arabic numerals:    ١٢٠, ٣٥٠
- Arabic words:       مية وعشرين (120), تلاتمية وخمسين (350), ألف (1000),
                      خمستاشر ألف (15000), عشرة (10), خمسة وعشرين (25),
                      ميتين (200), تلاتة آلاف (3000)

## Transaction type rules
Classify each transaction as "expense" or "income" based on context:

expense keywords: دفعت, اشتريت, صرفت, خدت, اتكلفت, بـ, فلوس على
income keywords:  قبضت, استلمت, حولولي, مرتبي, راتبي, دخلي, جالي, حصلت على

## Currency rules
- If the user says: جنيه / جنيه مصري / EGP / LE / جنيهات → use "EGP"
- If no currency is mentioned → default to "EGP" (Egyptian app)
- Do NOT translate amounts or currencies into other languages

## Description rules
- Keep the description in Arabic exactly as the user said it
- Do NOT translate, rephrase, or categorize
- The description field must NEVER be empty — always include what the user mentioned
- If the user did not name a specific item, use a generic label like "مبلغ" (amount)
- Examples:  "أوبر" stays "أوبر",  "كتاب" stays "كتاب",  "أكل" stays "أكل"

## Multiple transactions
A single transcript may contain multiple transactions joined by و / وكمان / وبعدين.
You MUST extract ALL of them as separate objects.

## No-transaction case
If the transcript contains no recognisable financial transaction, return an empty list.
Do NOT invent transactions.

## Output format
Return ONLY a JSON object — no markdown, no prose, no code fences.

Required JSON schema:
{{
  "transactions": [
    {{
      "amount": <positive number>,
      "currency": "<ISO code, e.g. EGP>",
      "description": "<Arabic description as spoken>",
      "transaction_type": "<expense | income>"
    }}
  ]
}}

If no transactions found:
{{
  "transactions": []
}}
"""

_HUMAN_TEMPLATE = "Transcript: {transcript}"

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ExtractionAgent:
    """
    LangChain-based Transaction Extraction Agent.

    By default the agent reads its configuration from the same environment
    variables used by the Orchestrator Agent:

        OLLAMA_API_KEY   – provider API key
        OLLAMA_BASE_URL  – OpenAI-compatible base URL (e.g. https://ollama.com/v1)
        OLLAMA_MODEL     – model identifier          (e.g. gpt-oss:120b)

    All three can be overridden via constructor arguments for testing.

    Parameters
    ----------
    model_name : str, optional
        Model identifier. Defaults to OLLAMA_MODEL env var.
    temperature : float, optional
        Sampling temperature. Kept at 0 for deterministic extraction.
    base_url : str, optional
        OpenAI-compatible endpoint. Defaults to OLLAMA_BASE_URL env var.
    api_key : str, optional
        API key. Defaults to OLLAMA_API_KEY env var.
    """

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL,
        temperature: float = 0.0,
        base_url: str = _DEFAULT_BASE_URL,
        api_key: str = _DEFAULT_API_KEY,
    ) -> None:
        self._llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
        )

        # JSON-schema mode — compatible with Ollama Cloud's /v1 endpoint.
        # Mirrors the same approach used in the Orchestrator Agent.
        structured_llm = self._llm.with_structured_output(
            ExtractionResult,
            method="json_schema",
        )

        self._prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", _HUMAN_TEMPLATE),
            ]
        )

        # Simple chain: prompt → structured LLM
        self._chain = self._prompt | structured_llm


    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def extract_transactions(self, transcript: str) -> ExtractionResult:
        """
        Extract all financial transactions from an Arabic transcript.

        This is the primary method that the backend workflow should call
        after the Orchestrator has classified the intent as ADD_TRANSACTION.

        Parameters
        ----------
        transcript : str
            The Arabic text produced by the STT service.
            Can be Egyptian Colloquial Arabic or Modern Standard Arabic.
            May contain multiple transactions in one sentence.

        Returns
        -------
        ExtractionResult
            A validated Pydantic model containing:
            - transactions : List[Transaction]
              Each Transaction has: amount, currency, description, transaction_type.
              Empty list if no recognisable transactions are found.

        Notes
        -----
        - The Categorization Agent receives extraction_result.transactions.
        - This method does NOT assign categories.
        - This method does NOT access the database.

        Examples
        --------
        >>> agent = ExtractionAgent()
        >>> result = agent.extract_transactions("دفعت 120 جنيه أوبر")
        >>> result.transactions[0].amount
        120.0
        >>> result.transactions[0].description
        'أوبر'
        >>> result.transactions[0].transaction_type
        <TransactionType.EXPENSE: 'expense'>
        """
        if not transcript or not transcript.strip():
            logger.warning("extract_transactions() received an empty transcript.")
            return ExtractionResult(transactions=[])

        logger.debug("Extracting transactions from transcript: %r", transcript)

        result: ExtractionResult = self._invoke_with_fallback(transcript.strip())

        # Deterministic post-validation
        result = _validate_result(result)

        logger.info(
            "extracted=%d transactions from transcript=%r",
            len(result.transactions),
            transcript,
        )
        return result

    # ------------------------------------------------------------------
    # Internal chain invocation with graceful fallback
    # ------------------------------------------------------------------

    def _invoke_with_fallback(self, transcript: str) -> ExtractionResult:
        """
        Invoke the chain and handle ValidationError gracefully.

        If the structured output parser raises a ValidationError (e.g. the
        model returned an empty description for one transaction), we fall back
        to parsing the raw JSON from the last AIMessage and build the
        ExtractionResult item-by-item, skipping only the invalid items.
        """
        try:
            return self._chain.invoke({"transcript": transcript})
        except (ValidationError, Exception) as exc:
            logger.warning(
                "Structured parse failed (%s). Attempting raw-JSON fallback.",
                type(exc).__name__,
            )
            return self._raw_json_fallback(transcript)

    def _raw_json_fallback(self, transcript: str) -> ExtractionResult:
        """
        Re-invoke the plain LLM (no structured output), parse the JSON
        manually, and build ExtractionResult skipping invalid items.
        """
        plain_chain = self._prompt | self._llm
        response: AIMessage = plain_chain.invoke({"transcript": transcript})
        raw_text = response.content if hasattr(response, "content") else str(response)

        # Strip markdown code fences if present
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]

        try:
            data: Dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.error("Raw JSON fallback could not parse model output. Returning empty.")
            return ExtractionResult(transactions=[])

        transactions: List[Transaction] = []
        for item in data.get("transactions", []):
            try:
                # Apply a sensible default for missing/empty description
                if not item.get("description", "").strip():
                    item["description"] = "مبلغ"
                transactions.append(Transaction(**item))
            except (ValidationError, Exception) as e:
                logger.warning("Skipping invalid transaction item %r: %s", item, e)

        return ExtractionResult(transactions=transactions)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_result(result: ExtractionResult) -> ExtractionResult:
    """
    Apply deterministic validation rules after the LLM response.

    Rules enforced here (belt-and-suspenders on top of Pydantic):
    - transactions must be a list
    - each transaction.amount must be > 0
    - each transaction.currency must be non-empty
    - each transaction.description must be non-empty
    - each transaction.transaction_type must be "expense" or "income"

    Transactions that fail validation are dropped with a logged warning
    rather than raising an exception, so partial results are preserved.

    Returns a new, validated ExtractionResult.
    """
    if not isinstance(result.transactions, list):
        logger.error("LLM returned non-list transactions. Returning empty result.")
        return ExtractionResult(transactions=[])

    valid: List[Transaction] = []
    for i, tx in enumerate(result.transactions):
        # amount > 0
        if not isinstance(tx.amount, (int, float)) or tx.amount <= 0:
            logger.warning("Dropping transaction[%d]: invalid amount %r", i, tx.amount)
            continue
        # currency present
        if not tx.currency or not tx.currency.strip():
            logger.warning("Dropping transaction[%d]: missing currency", i)
            continue
        # description not empty
        if not tx.description or not tx.description.strip():
            logger.warning("Dropping transaction[%d]: empty description", i)
            continue
        # transaction_type is a valid enum member
        try:
            TransactionType(tx.transaction_type)
        except ValueError:
            logger.warning(
                "Dropping transaction[%d]: unknown type %r", i, tx.transaction_type
            )
            continue

        valid.append(tx)

    return ExtractionResult(transactions=valid)
