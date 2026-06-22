"""
db_manager.py — Permanent Trade History Storage (Zero-Setup Cloud JSON)
========================================================================
Solves the Render ephemeral filesystem problem:
  - Render wipes all local files on every restart/redeploy
  - trade_history.json is therefore lost on every code push
  - This module uses JSONBlob.com (a free, zero-auth cloud JSON store)
    so history is PERMANENT and survives restarts forever.

Self-Healing Design:
  - If the blob ever returns 404 (expired), the module automatically
    creates a BRAND NEW blob from local backup and updates the cached ID.
  - A background keep-alive thread pings the blob every 12 hours so it
    never goes idle and never gets garbage-collected.
"""

import os
import json
import requests
import time
import threading
import urllib3
from logger import app_logger

# Suppress insecure request warnings since we are disabling SSL verification for jsonblob
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ---------------------------------------------------------------------------
# Cloud DB Config — HARDCODED ID survives Render restarts & code deploys.
# Self-healer auto-creates a new blob if this one ever expires (404).
# ---------------------------------------------------------------------------
_FALLBACK_BLOB_ID = "019ef067-5b0c-7655-80e9-a78b4079a780"  # Provisioned 2026-06-22 with 13 trades
_BACKUP_BLOB_ID = "019ef082-6969-794f-ae32-e7f3b2690ab8"   # Secondary Backup Blob
_BLOB_ID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".blob_id_cache")
_blob_id = _FALLBACK_BLOB_ID
_connected = False
_keep_alive_started = False


def _get_active_blob_id() -> str:
    """Returns the active blob ID: validated env var > hardcoded fallback.

    IMPORTANT: If JSONBLOB_ID env var is set but points to an old/empty blob
    (from a previous session), we fall back to the hardcoded blob ID.
    This prevents stale Render env vars from breaking trade history.
    """
    env_id = os.environ.get("JSONBLOB_ID")
    if env_id and env_id != _FALLBACK_BLOB_ID:
        # Quick sanity check — verify the env var blob actually has our data
        try:
            test_url = f"https://jsonblob.com/api/jsonBlob/{env_id}"
            test_res = requests.get(test_url, headers={'Accept': 'application/json'},
                                    timeout=5, verify=False)
            if test_res.status_code == 200:
                test_data = test_res.json()
                if len(test_data.get("trades", [])) > 0:
                    app_logger.info(f"DB: Using JSONBLOB_ID env var blob (has {len(test_data['trades'])} trades).")
                    return env_id
                else:
                    app_logger.warning(f"DB: JSONBLOB_ID env var blob has 0 trades — falling back to hardcoded blob.")
            else:
                app_logger.warning(f"DB: JSONBLOB_ID env var blob returned HTTP {test_res.status_code} — falling back to hardcoded blob.")
        except Exception as e:
            app_logger.warning(f"DB: Could not validate JSONBLOB_ID env var: {e} — falling back to hardcoded blob.")

    return _FALLBACK_BLOB_ID


def _write_blob_id_cache(blob_id: str):
    """Persist the active blob ID to a cache file (survives process restarts)."""
    try:
        with open(_BLOB_ID_FILE, 'w') as f:
            f.write(blob_id)
    except Exception as e:
        app_logger.warning(f"DB: Could not write blob ID cache: {e}")


def _self_heal(local_backup: dict = None):
    """
    Self-healer: Called when the blob returns 404 (expired).
    Creates a brand new blob with data from local backup and updates the ID.
    """
    global _blob_id
    app_logger.warning("DB: Blob 404 detected — Self-healer triggered. Creating new blob...")

    restore_data = local_backup or {"max_equity": 0.0, "trades": []}

    # If no backup passed in, try to load from local JSON file
    if not local_backup:
        local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
        if os.path.exists(local_file):
            try:
                with open(local_file, 'r') as f:
                    restore_data = json.load(f)
                app_logger.info(f"DB: Self-healer loaded {len(restore_data.get('trades', []))} trades from local backup.")
            except Exception as e:
                app_logger.error(f"DB: Self-healer could not read local backup: {e}")

    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.post(
            "https://jsonblob.com/api/jsonBlob",
            json=restore_data,
            headers=headers,
            timeout=15,
            verify=False
        )
        location = res.headers.get("Location", "")
        new_blob_id = location.split("/")[-1]
        if new_blob_id:
            _blob_id = new_blob_id
            _write_blob_id_cache(new_blob_id)
            app_logger.info(f"DB: Self-healer created new blob: ...{new_blob_id[-8:]} with {len(restore_data.get('trades', []))} trades restored.")
            return True
        else:
            app_logger.error("DB: Self-healer failed — no Location header in response.")
    except Exception as e:
        app_logger.error(f"DB: Self-healer exception: {e}")
    return False


def _keep_alive_loop():
    """Background thread: pings the blob every 12 hours to prevent JSONBlob expiry."""
    while True:
        time.sleep(12 * 3600)  # 12 hours
        try:
            headers = {'Accept': 'application/json'}
            res = requests.get(_get_cloud_url(), headers=headers, timeout=10, verify=False)
            if res.status_code == 200:
                app_logger.info("DB: Keep-alive ping to Cloud DB — OK.")
            elif res.status_code == 404:
                app_logger.warning("DB: Keep-alive found blob 404. Auto self-healing...")
                _self_heal()
        except Exception as e:
            app_logger.warning(f"DB: Keep-alive ping failed: {e}")


def _start_keep_alive():
    """Start the keep-alive background thread (only once)."""
    global _keep_alive_started
    if not _keep_alive_started:
        _keep_alive_started = True
        t = threading.Thread(target=_keep_alive_loop, daemon=True)
        t.start()
        app_logger.info("DB: Keep-alive thread started (pings every 12h).")


def _connect():
    """Load the Blob ID and mark as connected."""
    global _blob_id, _connected
    if _connected:
        return True
    _blob_id = _get_active_blob_id()
    _connected = True
    app_logger.info(f"DB: Connected to Cloud DB (Blob: ...{_blob_id[-8:]})")
    _start_keep_alive()
    return True

def _get_cloud_url():
    return f"https://jsonblob.com/api/jsonBlob/{_blob_id}"

def _get_backup_url():
    return f"https://jsonblob.com/api/jsonBlob/{_BACKUP_BLOB_ID}"

def load_backup_data() -> dict:
    """Loads data exclusively from the secondary backup blob."""
    try:
        headers = {'Accept': 'application/json'}
        res = requests.get(_get_backup_url(), headers=headers, timeout=10, verify=False)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        app_logger.error(f"DB: Exception loading backup from Cloud: {e}")
    return None

def save_backup_data(data: dict) -> bool:
    """Saves data exclusively to the secondary backup blob."""
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.put(_get_backup_url(), json=data, headers=headers, timeout=15, verify=False)
        return res.status_code in [200, 201]
    except Exception as e:
        app_logger.error(f"DB: Exception saving backup to Cloud: {e}")
        return False

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
        elif res.status_code == 404:
            app_logger.error("DB: Blob 404 on load. Triggering self-heal...")
            if _self_heal():
                # Retry once after self-heal creates new blob
                res2 = requests.get(_get_cloud_url(), headers=headers, timeout=10, verify=False)
                if res2.status_code == 200:
                    data = res2.json()
                    app_logger.info(f"DB: Self-heal load success! {len(data.get('trades', []))} trades restored.")
                    return data
            return None
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
            app_logger.info("DB: Successfully synced to Cloud DB.")
            return True
        elif res.status_code == 404:
            app_logger.error("DB: Blob 404 on save. Triggering self-heal...")
            if _self_heal(local_backup=data):
                # Retry save to the newly created blob
                res2 = requests.put(_get_cloud_url(), json=data, headers=headers, timeout=10, verify=False)
                if res2.status_code in [200, 201]:
                    app_logger.info("DB: Self-heal save success!")
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
