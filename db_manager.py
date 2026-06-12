"""
db_manager.py — Permanent Trade History Storage via MongoDB Atlas
=================================================================
Solves the Render ephemeral filesystem problem:
  - Render wipes all local files on every restart/redeploy
  - trade_history.json is therefore lost on every code push
  - This module saves EVERY trade to MongoDB Atlas (free cloud DB)
    so history is PERMANENT and survives restarts forever.

Setup (one-time, 5 minutes):
  1. Go to https://cloud.mongodb.com → Sign up free
  2. Create a FREE cluster (M0 Sandbox — 512 MB free forever)
  3. Create a DB user → note username + password
  4. Network Access → Add 0.0.0.0/0 (allow all IPs, needed for Render)
  5. Cluster → Connect → Python → Copy the connection string
  6. In your Render dashboard → Environment → Add variable:
       MONGODB_URI = mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/delta_bot
  7. Redeploy. Done — all trades now stored permanently!

Fallback: If MONGODB_URI is not set, silently falls back to local JSON only.
"""

import os
import json
import time
from logger import app_logger

# ---------------------------------------------------------------------------
# Lazy import MongoDB so the app still works if pymongo is not installed yet
# ---------------------------------------------------------------------------
_client = None
_db = None
_collection = None
_connected = False


def _connect():
    """Attempt to connect to MongoDB Atlas. Returns True on success."""
    global _client, _db, _collection, _connected

    if _connected:
        return True

    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        app_logger.info("DB: MONGODB_URI not set — using local JSON only.")
        return False

    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        # Quick ping to verify connection
        _client.admin.command('ping')
        _db = _client["delta_bot"]
        _collection = _db["trade_history"]

        # Create index on date for fast queries
        _collection.create_index("date")
        _collection.create_index("exit_time")

        _connected = True
        app_logger.info("DB: Connected to MongoDB Atlas successfully!")
        return True

    except ImportError:
        app_logger.warning("DB: pymongo not installed. Run: pip install pymongo")
        return False
    except Exception as e:
        app_logger.error(f"DB: MongoDB connection failed: {e}")
        return False


def save_trade(trade_record: dict) -> bool:
    """
    Save a single trade record to MongoDB.
    Uses exit_time as a unique key to prevent duplicates.
    Returns True on success, False on failure.
    """
    if not _connect():
        return False

    try:
        # Use exit_time + call_symbol as unique ID to prevent duplicates on retry
        uid = f"{trade_record.get('exit_time', '')}_{trade_record.get('call_symbol', '')}"
        trade_record["_uid"] = uid

        # Upsert: insert if new, update if already exists (idempotent)
        _collection.update_one(
            {"_uid": uid},
            {"$set": trade_record},
            upsert=True
        )
        app_logger.info(f"DB: Trade saved to MongoDB. PnL=${trade_record.get('pnl', 0):.2f}")
        return True

    except Exception as e:
        app_logger.error(f"DB: Failed to save trade to MongoDB: {e}")
        return False


def load_all_trades() -> list:
    """
    Load ALL trades from MongoDB, sorted by exit_time ascending.
    Returns [] if connection fails (caller falls back to local JSON).
    """
    if not _connect():
        return []

    try:
        cursor = _collection.find({}, {"_id": 0, "_uid": 0}).sort("exit_time", 1)
        trades = list(cursor)
        app_logger.info(f"DB: Loaded {len(trades)} trades from MongoDB.")
        return trades

    except Exception as e:
        app_logger.error(f"DB: Failed to load trades from MongoDB: {e}")
        return []


def get_max_equity() -> float:
    """Get the stored max equity high-water mark from MongoDB."""
    if not _connect():
        return 0.0

    try:
        doc = _db["metadata"].find_one({"_id": "max_equity"})
        if doc:
            return float(doc.get("value", 0.0))
        return 0.0
    except Exception as e:
        app_logger.error(f"DB: Failed to load max_equity: {e}")
        return 0.0


def save_max_equity(value: float):
    """Save the max equity high-water mark to MongoDB."""
    if not _connect():
        return

    try:
        _db["metadata"].update_one(
            {"_id": "max_equity"},
            {"$set": {"value": value}},
            upsert=True
        )
    except Exception as e:
        app_logger.error(f"DB: Failed to save max_equity: {e}")


def sync_local_json_to_mongodb(json_path: str):
    """
    One-time migration: reads existing trade_history.json and uploads
    all trades to MongoDB. Safe to call repeatedly (upsert prevents duplicates).
    """
    if not _connect():
        return

    if not os.path.exists(json_path):
        return

    try:
        with open(json_path, 'r') as f:
            data = json.load(f)

        trades = data.get("trades", [])
        if not trades:
            return

        uploaded = 0
        for trade in trades:
            if save_trade(trade):
                uploaded += 1

        max_eq = data.get("max_equity", 0.0)
        if max_eq > 0:
            save_max_equity(max_eq)

        app_logger.info(f"DB: Migration complete — {uploaded}/{len(trades)} trades synced to MongoDB.")

    except Exception as e:
        app_logger.error(f"DB: Migration failed: {e}")


def is_connected() -> bool:
    """Returns True if MongoDB is available and connected."""
    return _connected or _connect()
