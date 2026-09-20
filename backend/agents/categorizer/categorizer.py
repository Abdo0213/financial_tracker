"""
categorizer.py
--------------
Core implementation of the Categorization Agent.

Public interface (called by the backend workflow after extraction):

    from agents.categorizer.categorizer import CategorizationAgent

    agent  = CategorizationAgent()
    result = agent.categorize_transactions(transactions)  # -> CategorizationResult

The agent receives a list of Transaction objects (from the Extraction Agent),
assigns exactly ONE standardized category to each, and returns a
CategorizationResult.  It does NOT modify any existing field.

Configuration is read from the same .env used by the other agents:

    OLLAMA_API_KEY   – API key for the LLM provider
    OLLAMA_BASE_URL  – OpenAI-compatible base URL  (default: https://ollama.com/v1)
    OLLAMA_MODEL     – Model name                   (default: gpt-oss:120b)
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from agents.extractor.schemas import Transaction, TransactionType
from .schemas import (
    Category,
    CategorizedTransaction,
    CategorizationResult,
)

# Load .env from project root (three levels up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

_DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
_DEFAULT_MODEL    = os.getenv("OLLAMA_MODEL",    "gpt-oss:120b")
_DEFAULT_API_KEY  = os.getenv("OLLAMA_API_KEY",  os.getenv("OPENAI_API_KEY", ""))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal LLM response schema
#
# We ask the LLM to return ONLY a list of category strings — one per
# transaction — keeping the prompt tight and avoiding any risk of the LLM
# modifying other fields.  We reconstruct the full CategorizedTransaction
# objects deterministically in Python.
# ---------------------------------------------------------------------------


class _CategoryList(BaseModel):
    """Internal schema: the LLM returns only a list of category strings."""

    categories: List[str] = Field(
        ...,
        description=(
            "One category string per input transaction, in the same order. "
            "Each must be one of: food, transportation, shopping, education, "
            "healthcare, entertainment, bills, housing, income, other."
        ),
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

# Build the category list dynamically from the enum so it stays in sync
_CATEGORY_VALUES = ", ".join(c.value for c in Category)

_SYSTEM_PROMPT = (
    "You are the Categorization Agent for an Arabic personal finance tracker.\n"
    "Your ONLY job is to assign exactly ONE category to each transaction you receive.\n"
    "\n"
    "## Allowed categories (you must use ONLY these values, exactly as written)\n"
    + _CATEGORY_VALUES + "\n"
    "\n"
    "## Category mapping guide\n"
    "\n"
    "### food\n"
    "Arabic keywords: مطعم, أكل, غداء, عشاء, فطار, فطور, كافيه, قهوه, بيتزا,\n"
    "                 شاورما, كشري, فول, طعام, سوبر ماركت, بقالة, كارفور, سبينس\n"
    "English: any restaurant, cafe, grocery store, food delivery (Talabat, Uber Eats)\n"
    "\n"
    "### transportation\n"
    "Arabic keywords: أوبر, تاكسي, كريم, مترو, أتوبيس, ميكروباص, بنزين, وقود,\n"
    "                 موتور, توك توك, قطار, طيارة, بليط سفر, نقل\n"
    "English: Uber, Careem, taxi, fuel, public transport, flights\n"
    "\n"
    "### shopping\n"
    "Arabic keywords: ملابس, هدوم, جزمة, شنطة, اكسسوارات, موبايل, لابتوب,\n"
    "                 تليفزيون, جهاز, إيكيا, H&M, Zara, موبيليا\n"
    "English: clothes, electronics, furniture, accessories, general retail\n"
    "\n"
    "### education\n"
    "Arabic keywords: كتاب, كتب, كورس, دورة, جامعة, مدرسة, مصاريف دراسة,\n"
    "                 اشتراك تعليمي, Udemy, Coursera\n"
    "English: books, courses, tuition, school/university fees\n"
    "\n"
    "### healthcare\n"
    "Arabic keywords: صيدلية, دواء, دكتور, طبيب, مستشفى, عيادة, تحليل, أشعة,\n"
    "                 نظارة, عملية\n"
    "English: pharmacy, doctor, hospital, lab tests, glasses\n"
    "\n"
    "### entertainment\n"
    "Arabic keywords: سينما, تذكرة, Netflix, Spotify, لعبة, بلايستيشن, Xbox,\n"
    "                 كتاب روايات, رحلة ترفيهية, حفلة\n"
    "English: cinema, streaming, gaming, concerts, recreational trips\n"
    "\n"
    "### bills\n"
    "Arabic keywords: كهرباء, مياه, غاز, إنترنت, موبايل, تليفون, فاتورة,\n"
    "                 اشتراك, We, Vodafone, Orange, Etisalat\n"
    "English: electricity, water, gas, internet, phone bills, subscriptions\n"
    "\n"
    "### housing\n"
    "Arabic keywords: إيجار, أيجار, إيجار شقة, إيجار عقار, صيانة, عمارة\n"
    "English: rent, mortgage payments, building maintenance\n"
    "\n"
    "### income\n"
    "Arabic keywords: مرتب, راتب, مصروف, حوالة, بونص, فريلانس, شغل, معاش\n"
    "English: salary, freelance income, money received/transferred in\n"
    "Note: use this for ALL income transaction_type transactions unless another\n"
    "      category clearly applies.\n"
    "\n"
    "### other\n"
    "Use when the description does not clearly fit any category above.\n"
    "When in doubt, prefer 'other' over guessing.\n"
    "\n"
    "## Rules\n"
    "1. Return EXACTLY one category per transaction, in the SAME ORDER as the input.\n"
    "2. Do NOT modify amounts, descriptions, currencies, or transaction types.\n"
    "3. Do NOT invent a category outside the allowed list.\n"
    "4. For income transactions (transaction_type = income), default to 'income'\n"
    "   unless the description clearly suggests another category.\n"
    "5. Return ONLY a JSON object — no markdown, no prose, no code fences.\n"
    "\n"
    "## Required JSON schema\n"
    '{"categories": ["<category_1>", "<category_2>", ...]}\n'
    "\n"
    "The array length MUST equal the number of transactions you receive.\n"
)


_HUMAN_TEMPLATE = """\
Categorize the following {count} transaction(s). Return one category per item in order.

Transactions:
{transactions_json}
"""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CategorizationAgent:
    """
    LangChain-based Categorization Agent for the Arabic personal finance tracker.

    Reads LLM configuration from the same environment variables as the other
    agents:

        OLLAMA_API_KEY   – provider API key
        OLLAMA_BASE_URL  – OpenAI-compatible base URL (e.g. https://ollama.com/v1)
        OLLAMA_MODEL     – model identifier          (e.g. gpt-oss:120b)

    All three can be overridden via constructor arguments for testing.

    Parameters
    ----------
    model_name : str, optional
        Model identifier. Defaults to OLLAMA_MODEL env var.
    temperature : float, optional
        Sampling temperature. Kept at 0 for deterministic categorization.
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
        # We ask only for a list of category strings; full transaction
        # reconstruction happens deterministically in Python.
        structured_llm = self._llm.with_structured_output(
            _CategoryList,
            method="json_schema",
        )

        from langchain_core.messages import SystemMessage
        from langchain_core.prompts import HumanMessagePromptTemplate

        # Build the prompt so that:
        # - The system message is a pre-built SystemMessage (never parsed for
        #   variables, so any {word} in _SYSTEM_PROMPT is safe).
        # - Only the human turn goes through template substitution.
        self._system_message = SystemMessage(content=_SYSTEM_PROMPT)
        self._human_prompt = HumanMessagePromptTemplate.from_template(_HUMAN_TEMPLATE)

        self._prompt = ChatPromptTemplate.from_messages(
            [self._system_message, self._human_prompt]
        )

        self._chain = self._prompt | structured_llm

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def categorize_transactions(
        self, transactions: List[Transaction]
    ) -> CategorizationResult:
        """
        Assign a category to every transaction in the input list.

        This is the primary method the backend workflow should call after
        extraction.

        Parameters
        ----------
        transactions : List[Transaction]
            The transactions produced by the Transaction Extraction Agent
            (agents.extractor.schemas.Transaction objects).

        Returns
        -------
        CategorizationResult
            A validated Pydantic model whose ``transactions`` list contains
            CategorizedTransaction objects — one per input item, in the same
            order, with all original fields preserved and one ``category``
            field added.

        Notes
        -----
        - The count of output transactions always equals the count of inputs.
        - No existing field is modified: amount, currency, description, and
          transaction_type are copied verbatim.
        - This method does NOT access the database.
        - This method does NOT modify amounts or descriptions.

        Examples
        --------
        >>> from agents.extractor.schemas import Transaction
        >>> agent = CategorizationAgent()
        >>> txns = [Transaction(amount=120, currency="EGP",
        ...                     description="أوبر", transaction_type="expense")]
        >>> result = agent.categorize_transactions(txns)
        >>> result.transactions[0].category
        <Category.TRANSPORTATION: 'transportation'>
        """
        if not transactions:
            logger.info("categorize_transactions() called with empty list.")
            return CategorizationResult(transactions=[])

        logger.debug("Categorizing %d transaction(s).", len(transactions))

        categories = self._get_categories(transactions)

        # Rebuild full CategorizedTransaction objects deterministically
        result = _build_result(transactions, categories)

        # Deterministic post-validation
        result = _validate_result(transactions, result)

        logger.info(
            "categorized %d transaction(s): %s",
            len(result.transactions),
            [t.category.value for t in result.transactions],
        )
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_categories(self, transactions: List[Transaction]) -> List[str]:
        """
        Call the LLM and return a list of raw category strings.
        Falls back to raw-JSON parsing if structured output fails.
        """
        txn_dicts = [
            {
                "description": t.description,
                "transaction_type": t.transaction_type.value
                if hasattr(t.transaction_type, "value")
                else t.transaction_type,
            }
            for t in transactions
        ]
        payload = {
            "count": len(transactions),
            "transactions_json": json.dumps(txn_dicts, ensure_ascii=False, indent=2),
        }

        try:
            response: _CategoryList = self._chain.invoke(payload)
            return response.categories
        except (ValidationError, Exception) as exc:
            logger.warning(
                "Structured parse failed (%s). Attempting raw-JSON fallback.",
                type(exc).__name__,
            )
            return self._raw_json_fallback(payload, len(transactions))

    def _raw_json_fallback(
        self, payload: Dict[str, Any], expected_count: int
    ) -> List[str]:
        """
        Re-invoke the plain LLM, parse JSON manually, and return category list.
        If parsing fails, returns 'other' for every transaction.
        """
        plain_chain = self._prompt | self._llm
        try:
            response: AIMessage = plain_chain.invoke(payload)
            raw = response.content if hasattr(response, "content") else str(response)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            data: Dict[str, Any] = json.loads(raw)
            cats = data.get("categories", [])
            if isinstance(cats, list):
                return cats
        except Exception as e:
            logger.error("Raw-JSON fallback failed: %s. Defaulting all to 'other'.", e)

        return ["other"] * expected_count


# ---------------------------------------------------------------------------
# Module-level helpers (pure functions — no LLM calls)
# ---------------------------------------------------------------------------


def _resolve_category(raw: str, transaction_type: str) -> Category:
    """
    Map a raw string returned by the LLM to a Category enum member.

    - If the string is a valid Category value, use it.
    - If not, fall back to 'income' for income transactions, 'other' otherwise.
    """
    try:
        return Category(raw.strip().lower())
    except ValueError:
        logger.warning(
            "LLM returned unknown category %r. "
            "Falling back to 'income'/'other'.",
            raw,
        )
        if transaction_type in ("income", TransactionType.INCOME):
            return Category.INCOME
        return Category.OTHER


def _build_result(
    transactions: List[Transaction], categories: List[str]
) -> CategorizationResult:
    """
    Zip transactions with their category strings and build CategorizedTransaction
    objects. All original fields are copied verbatim.

    If the LLM returned fewer categories than transactions (length mismatch),
    the remaining transactions are assigned 'other' / 'income'.
    """
    categorized: List[CategorizedTransaction] = []

    for i, txn in enumerate(transactions):
        raw_cat = categories[i] if i < len(categories) else ""
        category = _resolve_category(raw_cat, txn.transaction_type)

        categorized.append(
            CategorizedTransaction(
                amount=txn.amount,
                currency=txn.currency,
                description=txn.description,
                transaction_type=txn.transaction_type,
                category=category,
            )
        )

    return CategorizationResult(transactions=categorized)


def _validate_result(
    original: List[Transaction],
    result: CategorizationResult,
) -> CategorizationResult:
    """
    Apply deterministic post-validation rules (belt-and-suspenders on top of
    Pydantic):

    1. Output count must equal input count.
    2. Each category must be a valid Category enum member.
    3. amount, description, and transaction_type must be unchanged.

    Transactions that fail field-integrity checks are logged as errors but
    the value is kept (the LLM must not be trusted to modify those fields,
    and we already reconstruct them ourselves, so this is mainly a sanity check).
    """
    if len(result.transactions) != len(original):
        logger.error(
            "Count mismatch: input=%d output=%d. Padding with 'other'.",
            len(original),
            len(result.transactions),
        )
        # Pad any missing entries
        existing = list(result.transactions)
        for txn in original[len(existing):]:
            cat = Category.INCOME if txn.transaction_type == TransactionType.INCOME else Category.OTHER
            existing.append(
                CategorizedTransaction(
                    amount=txn.amount,
                    currency=txn.currency,
                    description=txn.description,
                    transaction_type=txn.transaction_type,
                    category=cat,
                )
            )
        result = CategorizationResult(transactions=existing)

    for i, (orig, cat_txn) in enumerate(zip(original, result.transactions)):
        if cat_txn.amount != orig.amount:
            logger.error("transaction[%d] amount was modified by LLM. Restoring.", i)
        if cat_txn.description != orig.description:
            logger.error("transaction[%d] description was modified by LLM. Restoring.", i)
        if cat_txn.transaction_type != orig.transaction_type:
            logger.error("transaction[%d] transaction_type was modified by LLM. Restoring.", i)

        # Validate category is a known enum member (Pydantic already does this,
        # but we guard defensively here)
        try:
            Category(cat_txn.category)
        except ValueError:
            logger.error(
                "transaction[%d] has invalid category %r. Setting to 'other'.",
                i,
                cat_txn.category,
            )

    return result
