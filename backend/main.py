from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
