"""
Database Manager - GitHub Gists Edition (with JSONBlob fallback)
Permanently stores bot state and active positions in a private GitHub Gist.
If GITHUB_PAT is missing, falls back to JSONBlob so Render restarts don't wipe data.
"""

import json
import os
import requests
import threading
import time
from logger import app_logger
from utils import get_ist_now

# Environment Variables
GITHUB_PAT = os.environ.get("GITHUB_PAT")
GITHUB_GIST_ID = os.environ.get("GITHUB_GIST_ID")

_MASTER_JSONBLOB_ID = "019f73ca-cf4b-7663-9864-9bf01fe15970"
JSONBLOB_ID = None

# Local files for fallback and caching
BOT_STATE_FILE = "bot_state.json"
ACTIVE_POS_FILE = "active_positions.json"
CONFIG_FILE = "cloud_db_config.json"
_LAST_BACKUP_TIME_FILE = ".last_backup_time"

_connected = False
_sync_lock = threading.Lock()

def _get_headers():
    if not GITHUB_PAT:
        return None
    return {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github.v3+json"
    }

def _load_config():
    global GITHUB_GIST_ID, JSONBLOB_ID
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                if data.get("provider") == "github_gists" and not GITHUB_GIST_ID:
                    GITHUB_GIST_ID = data.get("gist_id")
                elif data.get("provider") == "jsonblob" and not JSONBLOB_ID:
                    JSONBLOB_ID = data.get("jsonblob_id")
        except Exception as e:
            app_logger.error(f"DB: Failed to load config - {e}")
            
    # CRITICAL: Always override JSONBLOB_ID from Master Blob to survive Render wipes
    if not GITHUB_PAT:
        try:
            url = f"https://jsonblob.com/api/jsonBlob/{_MASTER_JSONBLOB_ID}"
            res = requests.get(url, headers={'Accept': 'application/json'}, timeout=5)
            if res.status_code == 200:
                master_data = res.json()
                active_id = master_data.get("active_jsonblob_id")
                if active_id:
                    JSONBLOB_ID = active_id
                    app_logger.info(f"DB: Recovered Active JSONBLOB_ID from Master Blob: {JSONBLOB_ID}")
        except Exception as e:
            app_logger.error(f"DB: Failed to fetch Master Blob: {e}")

def _save_config(provider, identifier):
    try:
        key = "gist_id" if provider == "github_gists" else "jsonblob_id"
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"provider": provider, key: identifier}, f, indent=4)
            
        if provider == "jsonblob":
            # Update Master Blob
            url = f"https://jsonblob.com/api/jsonBlob/{_MASTER_JSONBLOB_ID}"
            requests.put(url, json={"active_jsonblob_id": identifier}, headers={'Content-Type': 'application/json', 'Accept': 'application/json'}, timeout=5)
    except Exception as e:
        pass

def _create_gist(bot_state_content, active_pos_content):
    """Creates a new private Gist and returns its ID."""
    global GITHUB_GIST_ID
    headers = _get_headers()
    if not headers:
        return None
        
    payload = {
        "description": "Delta BTC Options Bot - Master DB",
        "public": False,
        "files": {
            "bot_state.json": {"content": bot_state_content},
            "active_positions.json": {"content": active_pos_content}
        }
    }
    
    try:
        res = requests.post("https://api.github.com/gists", headers=headers, json=payload, timeout=10)
        if res.status_code == 201:
            gist_id = res.json()["id"]
            GITHUB_GIST_ID = gist_id
            _save_config("github_gists", gist_id)
            app_logger.warning(f"\n======================================================\n"
                               f"DB: NEW GIST CREATED SUCCESSFULLY!\n"
                               f"DB: GIST ID: {gist_id}\n"
                               f"DB: Add GITHUB_GIST_ID={gist_id} to Render Env Vars!\n"
                               f"======================================================")
            return gist_id
    except Exception as e:
        app_logger.error(f"DB: Exception creating Gist: {e}")
    return None

def _update_gist(files_dict):
    headers = _get_headers()
    if not headers or not GITHUB_GIST_ID:
        return False
        
    payload = {
        "description": f"Delta BTC Bot - Updated {get_ist_now().strftime('%d %b %H:%M')}",
        "files": files_dict
    }
    
    try:
        url = f"https://api.github.com/gists/{GITHUB_GIST_ID}"
        res = requests.patch(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            _write_last_backup_time()
            return True
        elif res.status_code == 404:
            app_logger.error("DB: Gist 404! Recreating Gist...")
            _create_gist(files_dict.get('bot_state.json', {}).get('content', '{}'),
                         files_dict.get('active_positions.json', {}).get('content', '{}'))
    except Exception as e:
        app_logger.error(f"DB: Exception updating Gist: {e}")
    return False

def _fetch_gist_file(filename):
    headers = _get_headers()
    if not headers or not GITHUB_GIST_ID:
        return None
        
    try:
        url = f"https://api.github.com/gists/{GITHUB_GIST_ID}"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            files = data.get("files", {})
            if filename in files:
                content = files[filename].get("content", "")
                return json.loads(content)
            return {} 
        elif res.status_code == 404:
            return None
    except Exception as e:
        app_logger.error(f"DB: Exception fetching Gist {filename}: {e}")
    return None

# --- JSONBLOB FALLBACK ---

def _create_jsonblob(data: dict) -> str:
    global JSONBLOB_ID
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        res = requests.post("https://jsonblob.com/api/jsonBlob", json=data, headers=headers, timeout=10)
        if res.status_code in [200, 201]:
            location = res.headers.get("Location", "")
            new_id = location.split("/")[-1]
            if new_id:
                JSONBLOB_ID = new_id
                _save_config("jsonblob", new_id)
                app_logger.warning(f"DB: Fallback JSONBlob Created! ID: {new_id}")
                return new_id
    except Exception as e:
        app_logger.error(f"DB: Failed to create JSONBlob: {e}")
    return None

def _update_jsonblob(data: dict) -> bool:
    if not JSONBLOB_ID:
        return False
    try:
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        url = f"https://jsonblob.com/api/jsonBlob/{JSONBLOB_ID}"
        res = requests.put(url, json=data, headers=headers, timeout=10)
        if res.status_code in [200, 201]:
            _write_last_backup_time()
            return True
        elif res.status_code == 404:
            app_logger.error("DB: JSONBlob 404! Recreating...")
            _create_jsonblob(data)
    except Exception as e:
        app_logger.error(f"DB: Exception updating JSONBlob: {e}")
    return False

def _fetch_jsonblob():
    if not JSONBLOB_ID:
        return None
    try:
        headers = {'Accept': 'application/json'}
        url = f"https://jsonblob.com/api/jsonBlob/{JSONBLOB_ID}"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        app_logger.error(f"DB: Exception fetching JSONBlob: {e}")
    return None

# -------------------------

def _write_last_backup_time():
    try:
        now_str = get_ist_now().strftime("%d %b, %H:%M IST")
        with open(_LAST_BACKUP_TIME_FILE, 'w') as f:
            f.write(now_str)
    except:
        pass

def get_last_backup_time() -> str:
    if os.path.exists(_LAST_BACKUP_TIME_FILE):
        try:
            with open(_LAST_BACKUP_TIME_FILE, 'r') as f:
                return f.read().strip()
        except:
            pass
    return "Never"

def _connect():
    global _connected
    _load_config()
    
    if GITHUB_PAT:
        if not GITHUB_GIST_ID:
            app_logger.warning("DB: GITHUB_GIST_ID missing. Will create a new Gist on first save.")
        else:
            app_logger.info(f"DB: Connected to GitHub Gist: ...{GITHUB_GIST_ID[-8:]}")
    else:
        app_logger.warning("DB: GITHUB_PAT missing! Activating JSONBlob Fallback Mode.")
        if not JSONBLOB_ID:
            app_logger.warning("DB: JSONBLOB_ID missing. Will create a new JSONBlob on first save.")
        else:
            app_logger.info(f"DB: Connected to JSONBlob Fallback: ...{JSONBLOB_ID[-8:]}")
            
    _connected = True

# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def load_all_data() -> dict:
    """Loads trade_history, daily_reports, and bot_state from Cloud."""
    with _sync_lock:
        if not _connected: _connect()
        
        # 1. Try Cloud
        data = None
        if GITHUB_PAT:
            data = _fetch_gist_file("bot_state.json")
        elif JSONBLOB_ID:
            blob_data = _fetch_jsonblob()
            if blob_data:
                data = blob_data.get("bot_state", {})
                
        if data is not None:
            # Overwrite local fallback files so they stay in sync
            try:
                with open(BOT_STATE_FILE, 'w') as f: json.dump(data, f, indent=4)
            except: pass
            
            if 'trade_history' in data and 'trades' not in data:
                data['trades'] = data.pop('trade_history')
            return data
            
        # 2. Fallback to Local
        app_logger.warning("DB: Cloud load failed. Falling back to local files.")
        local_data = {}
        
        try:
            if os.path.exists("trade_history.json"):
                with open("trade_history.json", 'r') as f:
                    th = json.load(f)
                    local_data['trades'] = th.get("trades", [])
            elif os.path.exists(BOT_STATE_FILE):
                 with open(BOT_STATE_FILE, 'r') as f:
                    bs = json.load(f)
                    local_data['trades'] = bs.get("trade_history", [])
                    
            if os.path.exists("daily_reports.json"):
                with open("daily_reports.json", 'r') as f:
                    dr = json.load(f)
                    local_data['daily_reports'] = dr.get("reports", [])
                    
            # Auto-create Cloud DB if missing
            content_str = json.dumps(local_data, indent=4)
            if GITHUB_PAT and not GITHUB_GIST_ID:
                app_logger.info("DB: Bootstrapping new Gist from local data...")
                _create_gist(content_str, "{}")
            elif not GITHUB_PAT and not JSONBLOB_ID:
                app_logger.info("DB: Bootstrapping new JSONBlob from local data...")
                _create_jsonblob({"bot_state": local_data, "active_positions": {}})
                    
            return local_data
        except Exception as e:
            app_logger.error(f"DB: Local load failed: {e}")
            return {}

def save_all_data(trade_data: dict) -> bool:
    """Saves unified state to Cloud, merging with existing data."""
    with _sync_lock:
        if not _connected: _connect()
        
        # Merge unified state
        unified = {
            "max_equity": trade_data.get("max_equity", 0.0),
            "trade_history": trade_data.get("trades", []),
            "daily_reports": trade_data.get("daily_reports", []),
            "state": trade_data.get("state", {})
        }
        
        # Save local fallback
        try:
            with open(BOT_STATE_FILE, 'w') as f: json.dump(unified, f, indent=4)
            with open("trade_history.json", 'w') as f: json.dump({"trades": unified["trade_history"], "max_equity": unified["max_equity"]}, f, indent=4)
            with open("daily_reports.json", 'w') as f: json.dump({"reports": unified["daily_reports"]}, f, indent=4)
        except Exception as e:
            app_logger.error(f"DB: Local save failed: {e}")
            
        if GITHUB_PAT:
            content_str = json.dumps(unified, indent=4)
            if not GITHUB_GIST_ID:
                _create_gist(content_str, "{}")
                return True
            return _update_gist({"bot_state.json": {"content": content_str}})
        else:
            # JSONBlob Fallback
            blob_data = _fetch_jsonblob() or {}
            blob_data["bot_state"] = unified
            if not JSONBLOB_ID:
                _create_jsonblob(blob_data)
                return True
            return _update_jsonblob(blob_data)

def load_active_positions() -> dict:
    """Loads active positions from Cloud."""
    with _sync_lock:
        if not _connected: _connect()
        
        data = None
        if GITHUB_PAT:
            data = _fetch_gist_file("active_positions.json")
        elif JSONBLOB_ID:
            blob_data = _fetch_jsonblob()
            if blob_data:
                data = blob_data.get("active_positions", {})
                
        if data is not None:
            return data
            
        if os.path.exists(ACTIVE_POS_FILE):
            try:
                with open(ACTIVE_POS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

def save_active_positions(positions: dict):
    """Saves active positions to Cloud."""
    with _sync_lock:
        if not _connected: _connect()
        content_str = json.dumps(positions, indent=4)
        
        try:
            with open(ACTIVE_POS_FILE, 'w') as f: f.write(content_str)
        except:
            pass
            
        if GITHUB_PAT:
            if not GITHUB_GIST_ID:
                _create_gist("{}", content_str)
            else:
                _update_gist({"active_positions.json": {"content": content_str}})
        else:
            blob_data = _fetch_jsonblob() or {}
            blob_data["active_positions"] = positions
            if not JSONBLOB_ID:
                _create_jsonblob(blob_data)
            else:
                _update_jsonblob(blob_data)

def trigger_cloud_sync():
    app_logger.info("DB: Manual Cloud Sync Triggered")

def is_connected() -> bool:
    return True # We now always have a connection (either Gist or JSONBlob fallback)
