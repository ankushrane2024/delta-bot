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
_FALLBACK_BLOB_ID = "019f2c26-6318-711f-9349-99ce26627ac1"  # Merged 17 trades
_BACKUP_BLOB_ID = "019f2c26-6684-755f-8953-2e096f1d4673"   # Secondary Backup Blob
_LAST_BACKUP_TIME_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".last_backup_time")
_blob_id = _FALLBACK_BLOB_ID
_connected = False
_keep_alive_thread = None

def _get_master_dir() -> dict:
    """Fetches the Master Directory blob that contains pointers to the true active databases."""
    try:
        url = f"https://jsonblob.com/api/jsonBlob/{_MASTER_DIR_BLOB_ID}"
        res = requests.get(url, headers={'Accept': 'application/json'}, timeout=5, verify=False)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        app_logger.error(f"DB: Failed to fetch Master Directory: {e}")
    return {}

def _update_master_dir(updates: dict):
    """Updates the Master Directory blob with new database pointers."""
    try:
        current = _get_master_dir()
        current.update(updates)
        url = f"https://jsonblob.com/api/jsonBlob/{_MASTER_DIR_BLOB_ID}"
        res = requests.put(url, json=current, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            app_logger.info("DB: Successfully updated Master Directory Blob.")
    except Exception as e:
        app_logger.error(f"DB: Failed to update Master Directory: {e}")

def _get_active_blob_id() -> str:
    """
    Returns the active JSONBLOB_ID.
    Priority:
    1. Environment Variable JSONBLOB_ID (if valid)
    2. Master Directory's 'trade_history_blob'
    3. Hardcoded Fallback ID (17 trades)
    """
    global _blob_id

    # 1. Environment Variable override
    env_id = os.environ.get("JSONBLOB_ID")
    if env_id and env_id != _FALLBACK_BLOB_ID:
        try:
            test_url = f"https://jsonblob.com/api/jsonBlob/{env_id}"
            test_res = requests.get(test_url, headers={'Accept': 'application/json'}, timeout=5, verify=False)
            if test_res.status_code == 200:
                _blob_id = env_id
                return _blob_id
        except Exception:
            pass

    # 2. Master Directory override (Bulletproof Render persistence)
    master_dir = _get_master_dir()
    if 'trade_history_blob' in master_dir:
        master_id = master_dir['trade_history_blob']
        if master_id != _blob_id:
            _blob_id = master_id
            app_logger.info(f"DB: Using Master Directory Blob ID: {_blob_id}")
            return _blob_id
            
    # 3. Fallback
    _blob_id = _FALLBACK_BLOB_ID
    return _blob_id

def _write_blob_id_cache(blob_id: str):
    """Writes the newly generated blob ID to the Master Directory so it survives Render restarts."""
    global _blob_id
    _blob_id = blob_id
    _update_master_dir({"trade_history_blob": blob_id})
    app_logger.info(f"DB: Hardcoded new Blob ID {blob_id} into Master Directory.")


def _self_heal(local_backup: dict = None):
    """
    Self-healer: Called when the blob returns 404 (expired).
    Creates a brand new blob with data from local backup and updates the ID.
    """
    global _blob_id
    app_logger.warning("DB: Blob 404 detected — Self-healer triggered. Creating new blob...")

    restore_data = local_backup

    # Try to load from Secondary Cloud Backup first
    if not restore_data:
        app_logger.info("DB: Self-healer attempting to restore from Secondary Cloud Backup...")
        try:
            sec_data = load_backup_data()
            if sec_data and sec_data.get('trades'):
                restore_data = sec_data
                app_logger.info(f"DB: Self-healer loaded {len(sec_data['trades'])} trades from Secondary Cloud Backup.")
        except Exception as e:
            app_logger.error(f"DB: Self-healer secondary cloud read failed: {e}")

    # If no backup passed in or cloud failed, try to load from local JSON file
    if not restore_data:
        local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_history.json")
        if os.path.exists(local_file):
            try:
                with open(local_file, 'r') as f:
                    restore_data = json.load(f)
                app_logger.info(f"DB: Self-healer loaded {len(restore_data.get('trades', []))} trades from local backup.")
            except Exception as e:
                app_logger.error(f"DB: Self-healer could not read local backup: {e}")
                
    if not restore_data:
        restore_data = {"max_equity": 0.0, "trades": []}

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

def _get_active_backup_blob_id() -> str:
    """Returns the ID for the secondary backup blob from the Master Directory."""
    master_dir = _get_master_dir()
    return master_dir.get("backup_blob", _BACKUP_BLOB_ID)

def _write_backup_blob_id(blob_id: str):
    """Saves a newly generated backup blob ID to the Master Directory."""
    _update_master_dir({"backup_blob": blob_id})

def _write_last_backup_time():
    """Updates the local timestamp cache for the last backup."""
    # We still use local cache for this timestamp since it's non-critical if lost.
    try:
        from utils import get_ist_now
        now_str = get_ist_now().strftime("%d %b, %H:%M IST")
        with open(_LAST_BACKUP_TIME_FILE, 'w') as f:
            f.write(now_str)
    except Exception:
        pass

def get_last_backup_time() -> str:
    if os.path.exists(_LAST_BACKUP_TIME_FILE):
        try:
            with open(_LAST_BACKUP_TIME_FILE, 'r') as f:
                return f.read().strip()
        except Exception:
            pass
    # If local file missing (Render reset), fetch from cloud
    try:
        res = requests.head(_get_backup_url(), timeout=5, verify=False)
        if res.status_code == 200:
            ts = res.headers.get('X-jsonblob-last-modified')
            if ts:
                dt = datetime.datetime.fromtimestamp(int(ts))
                return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        pass
    return "Never"

def _get_backup_url():
    return f"https://jsonblob.com/api/jsonBlob/{_get_active_backup_blob_id()}"

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
    """Saves data exclusively to the secondary backup blob. Self-heals if blob expires."""
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        url = _get_backup_url()
        res = requests.put(url, json=data, headers=headers, timeout=15, verify=False)
        
        if res.status_code in [200, 201]:
            _write_last_backup_time()
            return True
        elif res.status_code == 404:
            app_logger.warning("DB: Backup blob 404. Creating a new backup blob...")
            res2 = requests.post("https://jsonblob.com/api/jsonBlob", json=data, headers=headers, timeout=15, verify=False)
            location = res2.headers.get("Location", "")
            new_id = location.split("/")[-1]
            if new_id:
                _write_backup_blob_id(new_id)
                app_logger.info(f"DB: New backup blob created: ...{new_id[-8:]}")
                _write_last_backup_time()
                return True
        return False
    except Exception as e:
        app_logger.error(f"DB: Exception saving backup to Cloud: {e}")
        return False
def _gather_local_state() -> dict:
    """Reads local JSON state files to bundle them into a single cloud sync."""
    unified = {}
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    files_to_sync = [
        ('lot_size.json', 'lot_size'),
        ('bot_state.json', 'bot_state'),
        ('daily_reports.json', 'daily_reports'),
        ('trade_history.json', 'trade_history')
    ]
    for filename, key in files_to_sync:
        filepath = os.path.join(base_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    unified[key] = json.load(f)
            except Exception:
                unified[key] = {}
        else:
            unified[key] = {}
    return unified

def _unpack_local_state(unified: dict):
    """Writes the bundled cloud state back to local JSON files (for Render reboot recovery)."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    files_to_sync = [
        ('lot_size.json', 'lot_size'),
        ('bot_state.json', 'bot_state'),
        ('daily_reports.json', 'daily_reports'),
        ('trade_history.json', 'trade_history')
    ]
    for filename, key in files_to_sync:
        if key in unified and unified[key]:
            filepath = os.path.join(base_dir, filename)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(unified[key], f, indent=4)
            except Exception as e:
                app_logger.error(f"DB: Failed to unpack {filename}: {e}")


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
            
            # UNIFIED STATE CHECK
            if 'trade_history' in data:
                app_logger.info("DB: Unified state detected. Unpacking local files...")
                _unpack_local_state(data)
                trade_data = data['trade_history']
            else:
                trade_data = data
                
            app_logger.info(f"DB: Loaded {len(trade_data.get('trades', []))} trades from Cloud DB.")
            return trade_data
        elif res.status_code == 404:
            app_logger.error("DB: Blob 404 on load. Triggering self-heal...")
            if _self_heal():
                # Retry once after self-heal creates new blob
                res2 = requests.get(_get_cloud_url(), headers=headers, timeout=10, verify=False)
                if res2.status_code == 200:
                    data = res2.json()
                    
                    if 'trade_history' in data:
                        _unpack_local_state(data)
                        trade_data = data['trade_history']
                    else:
                        trade_data = data
                        
                    app_logger.info(f"DB: Self-heal load success! {len(trade_data.get('trades', []))} trades restored.")
                    return trade_data
            return None
        else:
            app_logger.error(f"DB: Failed to load from Cloud (HTTP {res.status_code})")
            return None
    except Exception as e:
        app_logger.error(f"DB: Exception loading from Cloud: {e}")
        return None

def save_all_data(trade_data: dict) -> bool:
    """
    Overwrite the entire database in the cloud with the unified state payload.
    JSONBlob uses PUT for full document replacement.
    """
    if not _connect():
        return False

    try:
        # Package everything into one payload
        unified = _gather_local_state()
        unified['trade_history'] = trade_data
        
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.put(_get_cloud_url(), json=unified, headers=headers, timeout=10, verify=False)
        
        if res.status_code in [200, 201]:
            app_logger.info("DB: Successfully synced to Cloud DB.")
            return True
        elif res.status_code == 404:
            app_logger.error("DB: Blob 404 on save. Triggering self-heal...")
            if _self_heal(local_backup=unified):
                # Retry save to the newly created blob
                res2 = requests.put(_get_cloud_url(), json=unified, headers=headers, timeout=10, verify=False)
                if res2.status_code in [200, 201]:
                    app_logger.info("DB: Self-heal save success!")
                    return True
        else:
            app_logger.error(f"DB: Failed to sync to Cloud (HTTP {res.status_code})")
            return False
    except Exception as e:
        app_logger.error(f"DB: Exception saving to Cloud DB: {e}")
        return False

def trigger_cloud_sync():
    """
    Forces a sync of all local state (lot_size, bot_state, daily_reports) to the cloud.
    
    CRITICAL SAFETY RULES:
    1. NEVER overwrite cloud trade_history with empty/smaller local data
    2. If local trade_history.json is missing (Render restart), fetch from cloud first
    3. Only update the non-trade state keys; preserve trade_history from cloud
    """
    if not _connect():
        return
    
    try:
        # Step 1: Fetch current cloud data to get the authoritative trade history
        headers = {'Accept': 'application/json'}
        res = requests.get(_get_cloud_url(), headers=headers, timeout=10, verify=False)
        
        if res.status_code == 200:
            cloud_data = res.json()
            
            # Extract the authoritative trade_history from cloud
            if 'trade_history' in cloud_data:
                cloud_trades = cloud_data['trade_history']
            elif 'trades' in cloud_data:
                cloud_trades = cloud_data
            else:
                cloud_trades = {"max_equity": 0.0, "trades": []}
        else:
            app_logger.warning(f"DB: trigger_cloud_sync — could not fetch cloud data (HTTP {res.status_code}). Skipping sync.")
            return
        
        # Step 2: Gather local state (lot_size, bot_state, daily_reports)
        local_state = _gather_local_state()
        
        # Step 3: Use LOCAL trade_history ONLY if it has MORE trades than cloud
        local_trades = local_state.get('trade_history', {})
        local_count = len(local_trades.get('trades', []))
        cloud_count = len(cloud_trades.get('trades', []))
        
        if local_count >= cloud_count and local_count > 0:
            final_trades = local_trades
            app_logger.info(f"DB: trigger_cloud_sync — using LOCAL trade_history ({local_count} trades >= cloud {cloud_count})")
        else:
            final_trades = cloud_trades
            if cloud_count > local_count:
                app_logger.info(f"DB: trigger_cloud_sync — PRESERVING CLOUD trade_history ({cloud_count} trades > local {local_count})")
        
        # Step 4: Save unified state with the SAFE trade_history
        save_all_data(final_trades)
        
    except Exception as e:
        app_logger.error(f"DB: trigger_cloud_sync failed: {e}")


def is_connected() -> bool:
    """Returns True if Cloud DB is configured."""
    return _connected or _connect()

# ---------------------------------------------------------------------------
# PAPER TRADING STATE PERSISTENCE
# Dedicated blob for active_positions to prevent history wipeouts
# ---------------------------------------------------------------------------
_ACTIVE_POS_BLOB_ID = "019f233f-1e6e-74de-857f-a7f211c3e2ac"

def save_active_positions(positions: dict):
    """Saves the active_positions dictionary to a dedicated cloud blob."""
    try:
        url = f"https://jsonblob.com/api/jsonBlob/{_ACTIVE_POS_BLOB_ID}"
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.put(url, json=positions, headers=headers, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            app_logger.info(f"DB: Saved {len(positions)} active positions to cloud.")
        else:
            app_logger.warning(f"DB: Failed to save active positions (HTTP {res.status_code})")
    except Exception as e:
        app_logger.warning(f"DB: Exception saving active positions: {e}")

def load_active_positions() -> dict:
    """Loads the active_positions dictionary from the dedicated cloud blob."""
    try:
        url = f"https://jsonblob.com/api/jsonBlob/{_ACTIVE_POS_BLOB_ID}"
        headers = {'Accept': 'application/json'}
        res = requests.get(url, headers=headers, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict):
                app_logger.info(f"DB: Loaded {len(data)} active positions from cloud.")
                return data
    except Exception as e:
        app_logger.warning(f"DB: Exception loading active positions: {e}")
    return {}

