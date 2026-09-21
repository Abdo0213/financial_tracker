"""
main.py
-------
FastAPI backend for the Financial Tracker Wallet.

Agentic workflow:
  1. Frontend uploads audio → /api/process_audio
  2. transcribe_audio() forwards the bytes to the Whisper STT service
  3. process_request() passes the transcript to the real agents:
       OrchestratorAgent  → classifies intent
       ExtractionAgent    → extracts Transaction objects (description, amount, currency, type)
       CategorizationAgent→ assigns one Category per transaction
  4. Results are mapped to the data.json schema and persisted; budget.spent is updated.

Fix log (vs. original stubs):
  FIX-1: Intent enum comparison — compare against Intent.ADD_TRANSACTION, not "add_transaction".
  FIX-2: Schema mismatch — map agent's `description` field → data.json's `title` field.
  FIX-3: Pipeline handoff — pass extraction_result.transactions (List), not the ExtractionResult object.
  FIX-4: Try/except around every agent invocation; graceful 503 error on LLM failure.
  FIX-5: Persist new transactions to data.json and recalculate budget.spent.
  FIX-6: transcribe_audio() reads WHISPER_API_URL from .env; raises RuntimeError with clear message if unset.
  FIX-7: Added POST /api/process_text for testing without audio.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Load environment variables
# ---------------------------------------------------------------------------
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

WHISPER_API_URL: Optional[str] = os.getenv("WHISPER_API_URL", "").strip() or None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent singletons — instantiated once at startup
# ---------------------------------------------------------------------------
import sys
sys.path.insert(0, os.path.dirname(__file__))

from agents.orchestrator import OrchestratorAgent, Intent
from agents.extractor import ExtractionAgent
from agents.categorizer import CategorizationAgent

try:
    _orchestrator = OrchestratorAgent()
    _extractor = ExtractionAgent()
    _categorizer = CategorizationAgent()
    logger.info("All agents initialised successfully.")
except Exception as _agent_init_err:
    logger.error("Agent initialisation failed: %s", _agent_init_err)
    _orchestrator = None
    _extractor = None
    _categorizer = None

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Financial Tracker Wallet API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")


def read_data() -> dict:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    """FIX-5: Persist updated data back to data.json atomically."""
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------
@app.get("/api/data")
async def get_data():
    return read_data()


@app.get("/api/budget")
async def get_budget():
    return read_data().get("budget", {})


@app.get("/api/transactions")
async def get_transactions():
    return read_data().get("transactions", [])


@app.get("/api/goals")
async def get_goals():
    return read_data().get("goals", [])


# ---------------------------------------------------------------------------
# Audio conversion + STT helpers
# ---------------------------------------------------------------------------
async def convert_audio_to_wav(audio_bytes: bytes) -> bytes:
    """
    Convert browser-recorded audio (OGG/OGX/Opus/WebM/MP4/etc.) to a
    predictable STT-friendly WAV stream: PCM 16-bit, mono, 16 kHz.

    Important: changing a filename from .ogx/.opus to .ogg does NOT convert
    the underlying bytes. FFmpeg performs the real container/codec conversion.
    """
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    try:
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-i", "pipe:0",
            "-vn",
            "-acodec", "pcm_s16le",
            "-ac", "1",
            "-ar", "16000",
            "-f", "wav",
            "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.error("FFmpeg executable was not found on the backend machine.")
        raise HTTPException(
            status_code=500,
            detail=(
                "FFmpeg is not installed on the backend machine. "
                "Install it with: sudo apt update && sudo apt install -y ffmpeg"
            ),
        )

    wav_bytes, stderr = await process.communicate(input=audio_bytes)

    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="ignore").strip()
        logger.error("FFmpeg audio conversion failed: %s", error_text)
        raise HTTPException(
            status_code=400,
            detail=f"Could not decode/convert the uploaded audio: {error_text or 'unknown FFmpeg error'}",
        )

    if not wav_bytes:
        raise HTTPException(
            status_code=400,
            detail="Audio conversion produced an empty WAV file.",
        )

    logger.info("Audio converted to WAV: %d -> %d bytes", len(audio_bytes), len(wav_bytes))
    return wav_bytes


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    content_type: str = "audio/wav",
) -> str:
    """
    FIX-6: Forward audio bytes to the Whisper STT service configured via
    WHISPER_API_URL.  Raises HTTPException(503) with a clear message if the
    env var is not set or the service is unreachable.
    """
    if not WHISPER_API_URL:
        raise HTTPException(
            status_code=503,
            detail=(
                "Whisper STT service not configured. "
                "Set WHISPER_API_URL in your .env file "
                "(e.g. WHISPER_API_URL=https://xxxx.ngrok-free.app)."
            ),
        )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{WHISPER_API_URL.rstrip('/')}/transcribe",
                files={"file": (filename, audio_bytes, content_type)},
                headers={"ngrok-skip-browser-warning": "true"},
            )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text", "").strip()
        if not text:
            raise HTTPException(
                status_code=502,
                detail="Whisper service returned an empty transcript.",
            )
        return text

    except httpx.HTTPStatusError as exc:
        logger.error("Whisper STT returned HTTP %s: %s", exc.response.status_code, exc.response.text)
        raise HTTPException(
            status_code=502,
            detail=f"Whisper service error: HTTP {exc.response.status_code}",
        )
    except httpx.RequestError as exc:
        logger.error("Whisper STT unreachable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Whisper service unreachable: {exc}",
        )


# ---------------------------------------------------------------------------
# Agentic workflow
# ---------------------------------------------------------------------------
def _check_agents() -> None:
    """FIX-4: Raise HTTP 503 with a clear message if agents failed to initialise."""
    if _orchestrator is None or _extractor is None or _categorizer is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI agents are not available. "
                "Check that OLLAMA_API_KEY (or OPENAI_API_KEY) is set in your .env file."
            ),
        )


def process_request(transcript: str) -> dict:
    """
    Run the full agentic pipeline for a transcript string.

    FIX-1: Intent compared against Intent enum members (not lowercase strings).
    FIX-3: extraction_result.transactions (List) passed into categorizer, not the object.
    FIX-4: Each agent call wrapped in try/except to produce clear 500 errors.
    FIX-5: Categorised transactions persisted to data.json; budget.spent recalculated.
    """
    _check_agents()

    # ── Step 1: Orchestrate intent ────────────────────────────────────────────
    try:
        orch_result = _orchestrator.orchestrate(transcript)
    except Exception as exc:
        logger.error("OrchestratorAgent failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Orchestrator agent error: {exc}",
        )

    intent: Intent = orch_result.intent
    logger.info("Intent classified: %s (confidence=%.2f)", intent.value, orch_result.confidence)

    # ── Step 2: Route by intent ───────────────────────────────────────────────
    # FIX-1: Compare against the Intent enum, not a plain lowercase string.
    if intent == Intent.ADD_TRANSACTION:
        # Step 3: Extract transactions
        try:
            extraction_result = _extractor.extract_transactions(transcript)
        except Exception as exc:
            logger.error("ExtractionAgent failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Extraction agent error: {exc}",
            )

        # FIX-3: Pass the List inside the result, not the ExtractionResult object.
        extracted_transactions = extraction_result.transactions

        if not extracted_transactions:
            return {
                "status": "success",
                "intent": intent.value,
                "transcript": transcript,
                "message": "No transactions could be extracted from the transcript.",
                "transactions": [],
            }

        # Step 4: Categorise
        try:
            categorization_result = _categorizer.categorize_transactions(extracted_transactions)
        except Exception as exc:
            logger.error("CategorizationAgent failed: %s", exc, exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Categorization agent error: {exc}",
            )

        categorized = categorization_result.transactions

        # FIX-5: Persist to data.json; update budget.spent
        saved = _persist_transactions(categorized)

        return {
            "status": "success",
            "intent": intent.value,
            "transcript": transcript,
            "transactions": saved,
        }

    elif intent == Intent.QUERY_TRANSACTIONS:
        data = read_data()
        txns = data.get("transactions", [])
        budget = data.get("budget", {})
        return {
            "status": "success",
            "intent": intent.value,
            "transcript": transcript,
            "message": (
                f"You have {len(txns)} transaction(s). "
                f"Budget spent: {budget.get('currency', '')} {budget.get('spent', 0):.2f} "
                f"of {budget.get('currency', '')} {budget.get('total', 0):.2f}."
            ),
            "transactions": txns[-10:],  # Return last 10
        }

    else:
        return {
            "status": "success",
            "intent": intent.value,
            "transcript": transcript,
            "message": (
                f"Intent '{intent.value}' recognised but not handled yet. "
                "Only ADD_TRANSACTION and QUERY_TRANSACTIONS are currently implemented."
            ),
        }


def _persist_transactions(categorized) -> List[dict]:
    """
    FIX-2: Map agent schema (description, currency, transaction_type) → data.json schema (title, category).
    FIX-5: Append to data.json and update budget.spent based on expense/income type.
    Returns the list of saved transaction dicts.
    """
    data = read_data()
    existing: list = data.get("transactions", [])

    # Determine next ID
    next_id = max((t.get("id", 0) for t in existing), default=0) + 1

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    saved = []
    spent_delta = 0.0

    for cat_txn in categorized:
        # FIX-2: Map `description` → `title`; category enum/str → lowercase string
        cat_val = getattr(cat_txn.category, "value", str(cat_txn.category)).lower()
        tx_type_val = getattr(cat_txn.transaction_type, "value", str(cat_txn.transaction_type)).lower()

        record = {
            "id": next_id,
            "title": cat_txn.description,          # agent uses `description`, data.json uses `title`
            "category": cat_val,
            "amount": cat_txn.amount,
            "currency": cat_txn.currency,
            "transaction_type": tx_type_val,
            "date": now_iso,
        }
        existing.append(record)
        saved.append(record)
        next_id += 1

        # FIX-5: Update budget.spent for expense transactions
        if tx_type_val == "expense":
            spent_delta += cat_txn.amount

    # Recalculate budget.spent
    budget = data.get("budget", {})
    budget["spent"] = round(budget.get("spent", 0.0) + spent_delta, 2)

    data["transactions"] = existing
    data["budget"] = budget
    save_data(data)

    logger.info(
        "Persisted %d transaction(s); budget.spent now = %.2f",
        len(saved),
        budget["spent"],
    )
    return saved


# ---------------------------------------------------------------------------
# POST endpoints
# ---------------------------------------------------------------------------

class TextRequest(BaseModel):
    text: str


@app.post("/api/process_text")
async def process_text(body: TextRequest):
    """
    FIX-7: Accept a plain text transcript for testing without audio.
    Runs the same agentic pipeline as /api/process_audio.
    """
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text field must not be empty.")
    return process_request(body.text.strip())


@app.post("/api/process_audio")
async def process_audio(file: UploadFile = File(...)):
    """
    Receive browser audio, convert it to 16 kHz mono WAV with FFmpeg, send the
    normalized WAV to the Whisper STT service, then run the agentic pipeline.

    This makes Firefox OGG/OGX/Opus recordings and Chrome WebM/Opus recordings
    follow exactly the same STT path.
    """
    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    logger.info(
        "Received audio upload: filename=%r content_type=%r size=%d bytes",
        file.filename,
        file.content_type,
        len(audio_bytes),
    )

    # Real conversion, not just an extension rename.
    wav_bytes = await convert_audio_to_wav(audio_bytes)

    transcript = await transcribe_audio(
        wav_bytes,
        filename="voice_input.wav",
        content_type="audio/wav",
    )

    return process_request(transcript)


# ---------------------------------------------------------------------------
# Frontend Static Files Mount
# ---------------------------------------------------------------------------
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

