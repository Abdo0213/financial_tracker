"""
orchestrator.py
---------------
Core implementation of the Orchestrator Agent.

Public interface (called by the backend):

    from agents.orchestrator.orchestrator import OrchestratorAgent

    agent = OrchestratorAgent()           # or pass model_name / temperature / base_url / api_key
    result = agent.orchestrate(transcript)  # -> OrchestratorResult

The agent classifies the user's intent from an Arabic speech-to-text
transcript and returns a structured OrchestratorResult.  It intentionally
does NOT extract amounts, categorize transactions, access the database,
or perform any financial calculations — those responsibilities belong to
downstream agents.

Configuration is read from environment variables (via .env):

    OLLAMA_API_KEY   – API key for the LLM provider (Ollama Cloud or OpenAI)
    OLLAMA_BASE_URL  – OpenAI-compatible base URL  (default: https://ollama.com/v1)
    OLLAMA_MODEL     – Model name                   (default: gpt-oss:120b)
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from .schemas import Intent, OrchestratorResult

# Load .env from the project root (two levels up from this file)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

_DEFAULT_BASE_URL = os.getenv("OLLAMA_BASE_URL", "https://ollama.com/v1")
_DEFAULT_MODEL    = os.getenv("OLLAMA_MODEL",    "gpt-oss:120b")
_DEFAULT_API_KEY  = os.getenv("OLLAMA_API_KEY",  os.getenv("OPENAI_API_KEY", ""))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Orchestrator of an Arabic personal finance tracker.
Your ONLY job is to classify the user's intent from a speech-to-text transcript.

You understand both Egyptian Colloquial Arabic (عامية مصرية) and Modern Standard Arabic (فصحى).

## Supported Intents

### 1. ADD_TRANSACTION
The user wants to record a new financial transaction (expense or income).
Examples:
- "دفعت 120 جنيه أوبر"            (I paid 120 pounds for Uber)
- "اشتريت كتاب بـ350 جنيه"          (I bought a book for 350 pounds)
- "قبضت 15000 جنيه"               (I received / got paid 15,000 pounds)
- "دفعت مية وعشرين جنيه في أوبر"    (I paid one hundred and twenty pounds for Uber)
- "أنا اشتريت عيش بعشرة جنيه"       (I bought bread for ten pounds)

### 2. QUERY_TRANSACTIONS
The user wants to view, search, or ask about existing transactions or spending summaries.
Examples:
- "أنا صرفت كام النهاردة؟"           (How much did I spend today?)
- "وريني مصاريفي"                   (Show me my expenses)
- "صرفي على الأكل كام؟"             (How much did I spend on food?)
- "إيه آخر عملية؟"                  (What is the last transaction?)
- "كام جنيه عندي في المحفظة؟"        (How much money do I have in my wallet?)

### 3. UPDATE_TRANSACTION
The user wants to correct or modify a previously recorded transaction.
Examples:
- "الأوبر اللي سجلته كان 150 مش 120" (The Uber I recorded was 150 not 120)
- "غير آخر عملية"                   (Change/edit the last transaction)
- "عدل مبلغ الأوبر"                  (Correct the Uber amount)

### 4. DELETE_TRANSACTION
The user wants to remove or cancel a previously recorded transaction.
Examples:
- "امسح آخر عملية"                  (Delete the last transaction)
- "احذف مصروف الأوبر"               (Delete the Uber expense)
- "إلغاء آخر معاملة"                 (Cancel the last transaction)

### 5. UNKNOWN
Use this intent when the transcript does not clearly belong to any of the above categories,
or when the request is completely unrelated to financial transactions.

## Rules
- Classify ONLY based on the user's intent. Do NOT extract amounts, categories, or any other data.
- Do NOT invent a new intent. You must return one of the five intents above.
- Set confidence to a value between 0.0 and 1.0. Use lower values when the intent is ambiguous.
- Write a brief reasoning in English explaining your classification.
- Return ONLY a JSON object — no markdown, no prose, no code fences.

## Required JSON schema
{{
  "intent":    "<one of: ADD_TRANSACTION | QUERY_TRANSACTIONS | UPDATE_TRANSACTION | DELETE_TRANSACTION | UNKNOWN>",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<short English explanation>"
}}"""

_HUMAN_TEMPLATE = "Transcript: {transcript}"

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class OrchestratorAgent:
    """
    LangChain-based Orchestrator Agent for the Arabic personal finance tracker.

    By default the agent reads its configuration from environment variables
    (populated from .env via python-dotenv):

        OLLAMA_API_KEY   – provider API key
        OLLAMA_BASE_URL  – OpenAI-compatible base URL (e.g. https://ollama.com/v1)
        OLLAMA_MODEL     – model identifier          (e.g. gpt-oss:120b)

    All three can be overridden via constructor arguments for testing.

    Parameters
    ----------
    model_name : str, optional
        Model identifier. Defaults to OLLAMA_MODEL env var (gpt-oss:120b).
    temperature : float, optional
        Sampling temperature. Kept at 0 for deterministic classification.
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
        llm = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            base_url=base_url,
            api_key=api_key,
        )

        # Use JSON-schema mode — compatible with Ollama Cloud's /v1 endpoint.
        # method="json_schema" sends response_format={type:"json_schema",...}
        # instead of OpenAI function-calling, which Ollama does not support.
        structured_llm = llm.with_structured_output(
            OrchestratorResult,
            method="json_schema",
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                ("human", _HUMAN_TEMPLATE),
            ]
        )

        # Simple chain: prompt → structured LLM
        self._chain = prompt | structured_llm

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def orchestrate(self, transcript: str) -> OrchestratorResult:
        """
        Classify the intent of an Arabic speech-to-text transcript.

        This is the primary method that the backend workflow should call.

        Parameters
        ----------
        transcript : str
            The Arabic text produced by the STT service.
            Can be in Egyptian Colloquial Arabic or Modern Standard Arabic.

        Returns
        -------
        OrchestratorResult
            A validated Pydantic model containing:
            - intent     (Intent enum)
            - confidence (float, 0.0 – 1.0)
            - reasoning  (str, English explanation for debugging)

        Raises
        ------
        ValueError
            If the LLM returns a response that cannot be validated against
            OrchestratorResult (e.g. an unsupported intent value).

        Examples
        --------
        >>> agent = OrchestratorAgent()
        >>> result = agent.orchestrate("دفعت 120 جنيه أوبر")
        >>> result.intent
        <Intent.ADD_TRANSACTION: 'ADD_TRANSACTION'>
        >>> result.confidence
        0.97
        """
        if not transcript or not transcript.strip():
            logger.warning("orchestrate() received an empty transcript.")
            return OrchestratorResult(
                intent=Intent.UNKNOWN,
                confidence=1.0,
                reasoning="Empty transcript provided.",
            )

        logger.debug("Orchestrating transcript: %r", transcript)

        result: OrchestratorResult = self._chain.invoke(
            {"transcript": transcript.strip()}
        )

        # Deterministic post-validation (belt-and-suspenders)
        result = _validate_result(result)

        logger.info(
            "intent=%s confidence=%.2f transcript=%r",
            result.intent.value,
            result.confidence,
            transcript,
        )
        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_result(result: OrchestratorResult) -> OrchestratorResult:
    """
    Apply deterministic validation rules after the LLM response.

    - intent must be one of the supported Intent values (Pydantic already
      enforces this, but we guard defensively).
    - confidence is clamped to [0.0, 1.0] (handled by the Pydantic validator,
      but we re-check here for clarity).

    Returns a new, validated OrchestratorResult.
    """
    # Validate intent membership
    try:
        validated_intent = Intent(result.intent)
    except ValueError:
        logger.error(
            "LLM returned unsupported intent '%s'. Falling back to UNKNOWN.",
            result.intent,
        )
        validated_intent = Intent.UNKNOWN

    # Clamp confidence (Pydantic validator already does this, but be explicit)
    validated_confidence = max(0.0, min(1.0, float(result.confidence)))

    return OrchestratorResult(
        intent=validated_intent,
        confidence=validated_confidence,
        reasoning=result.reasoning,
    )
