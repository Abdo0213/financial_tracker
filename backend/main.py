from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import json
import os

app = FastAPI(title="Financial Tracker Wallet API")

# Enable CORS for the frontend to access the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")

def read_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

@app.get("/api/data")
async def get_data():
    return read_data()

@app.get("/api/budget")
async def get_budget():
    data = read_data()
    return data.get("budget", {})

@app.get("/api/transactions")
async def get_transactions():
    data = read_data()
    return data.get("transactions", [])

@app.get("/api/goals")
async def get_goals():
    data = read_data()
    return data.get("goals", [])


# --- AGENTIC WORKFLOW MODELS & FUNCTIONS ---

class Transaction(BaseModel):
    title: str
    amount: float
    category: Optional[str] = None
    date: Optional[str] = None

class CategorizedTransaction(Transaction):
    category: str

# 2. STT communication
def transcribe_audio(audio_bytes: bytes) -> str:
    # TODO: Connect to Colab STT / Whisper model here
    print("Transcribing audio...")
    return "User said: I bought a coffee for 5 dollars."

# 4. Orchestrator
def orchestrate(transcript: str) -> str:
    # TODO: Connect to LLM to classify intent (e.g. 'add_transaction', 'query_balance')
    print(f"Orchestrating intent for transcript: {transcript}")
    return "add_transaction"

# 5. Transaction Extractor Agent
def extract_transactions(transcript: str) -> List[Transaction]:
    # TODO: Connect to LLM to extract entities
    print(f"Extracting transactions from: {transcript}")
    return [Transaction(title="Coffee", amount=5.0)]

# 6. Categorization Agent
def categorize_transactions(transactions: List[Transaction]) -> List[CategorizedTransaction]:
    # TODO: Connect to LLM to assign categories
    print(f"Categorizing transactions: {transactions}")
    categorized = []
    for t in transactions:
        categorized.append(CategorizedTransaction(
            title=t.title, 
            amount=t.amount, 
            category="Food", # Hardcoded dummy logic
            date=t.date
        ))
    return categorized

# 3. Agentic workflow entry
def process_request(transcript: str):
    intent = orchestrate(transcript)
    
    if intent == "add_transaction":
        transactions = extract_transactions(transcript)
        categorized = categorize_transactions(transactions)
        
        # Here we could update data.json to save the new transactions
        
        return {
            "status": "success",
            "intent": intent,
            "transcript": transcript,
            "transactions": categorized
        }
        
    return {
        "status": "success",
        "intent": intent,
        "transcript": transcript,
        "message": "Intent not handled yet."
    }

# 1. Entry point from frontend
@app.post("/api/process_audio")
async def process_audio(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    
    # Run the workflow
    transcript = transcribe_audio(audio_bytes)
    result = process_request(transcript)
    
    return result
