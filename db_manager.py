"""
db_manager.py — Permanent Trade History Storage (Zero-Setup Cloud JSON)
========================================================================
Solves the Render ephemeral filesystem problem:
  - Render wipes all local files on every restart/redeploy
  - trade_history.json is therefore lost on every code push
  - This module uses JSONBlob.com (a free, zero-auth cloud JSON store)
    so history is PERMANENT and survives restarts forever.
"""

import os
import json
import requests
import time
import urllib3
from logger import app_logger

# Suppress insecure request warnings since we are disabling SSL verification for jsonblob
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Cloud DB Config
# ---------------------------------------------------------------------------
_blob_id = "019eea90-751e-7ded-b0d0-73c302cf5a5c"  # HARDCODED PRO BACKUP DB
_connected = False

def _connect():
    """Load the Blob ID from environment variable (primary) or hardcoded fallback."""
    global _blob_id, _connected
    
    if _connected:
        return True

    # PRIMARY: Load from environment variable (survives Render restarts)
    env_blob_id = os.environ.get("JSONBLOB_ID")
    if env_blob_id:
        _blob_id = env_blob_id
        _connected = True
        app_logger.info("DB: Connected to Cloud DB via JSONBLOB_ID env var.")
        return True

    # FALLBACK: Use the hardcoded Blob ID
    if _blob_id:
        _connected = True
        app_logger.info("DB: Connected to Cloud DB via permanent hardcoded ID.")
        return True
            
    app_logger.warning("DB: Cloud DB not configured. Using local JSON only.")
    return False

def _get_cloud_url():
    return f"https://jsonblob.com/api/jsonBlob/{_blob_id}"

def load_all_data() -> dict:
    """
    Load the entire database from the cloud.
    Returns: {"max_equity": float, "trades": [dict, ...]} or None on network error.
    """
    if not _connect():
        return {}

    try:
        headers = {'Accept': 'application/json'}
        res = requests.get(_get_cloud_url(), headers=headers, timeout=10, verify=False)
        
        if res.status_code == 200:
            data = res.json()
            app_logger.info(f"DB: Loaded {len(data.get('trades', []))} trades from Cloud DB.")
            return data
        else:
            app_logger.error(f"DB: Failed to load from Cloud (HTTP {res.status_code})")
            return None
    except Exception as e:
        app_logger.error(f"DB: Exception loading from Cloud: {e}")
        return None

def save_all_data(data: dict) -> bool:
    """
    Overwrite the entire database in the cloud with the provided data.
    JSONBlob uses PUT for full document replacement.
    """
    if not _connect():
        return False

    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.put(_get_cloud_url(), json=data, headers=headers, timeout=10, verify=False)
        
        if res.status_code in [200, 201]:
            app_logger.info(f"DB: Successfully synced to Cloud DB.")
            return True
        else:
            app_logger.error(f"DB: Failed to sync to Cloud (HTTP {res.status_code})")
            return False
    except Exception as e:
        app_logger.error(f"DB: Exception saving to Cloud: {e}")
        return False

def is_connected() -> bool:
    """Returns True if Cloud DB is configured."""
    return _connected or _connect()
