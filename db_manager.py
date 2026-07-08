"""
Database Manager - GitHub Gists Edition
Permanently stores bot state and active positions in a private GitHub Gist.
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
    global GITHUB_GIST_ID
    if not GITHUB_GIST_ID and os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                if data.get("provider") == "github_gists":
                    GITHUB_GIST_ID = data.get("gist_id")
        except Exception as e:
            app_logger.error(f"DB: Failed to load config - {e}")

def _save_config(gist_id):
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"provider": "github_gists", "gist_id": gist_id}, f, indent=4)
    except Exception as e:
        pass

def _create_gist(bot_state_content, active_pos_content):
    """Creates a new private Gist and returns its ID."""
    global GITHUB_GIST_ID
    headers = _get_headers()
    if not headers:
        app_logger.error("DB: Missing GITHUB_PAT. Cannot create Gist.")
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
            _save_config(gist_id)
            app_logger.warning(f"\n======================================================\n"
                               f"DB: NEW GIST CREATED SUCCESSFULLY!\n"
                               f"DB: GIST ID: {gist_id}\n"
                               f"DB: Add GITHUB_GIST_ID={gist_id} to Render Env Vars!\n"
                               f"======================================================")
            return gist_id
        else:
            app_logger.error(f"DB: Failed to create Gist. {res.status_code} - {res.text}")
    except Exception as e:
        app_logger.error(f"DB: Exception creating Gist: {e}")
    return None

def _update_gist(files_dict):
    """Updates the existing Gist. files_dict format: {'filename.json': {'content': '...json...'}}"""
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
        else:
            app_logger.error(f"DB: Failed to update Gist {GITHUB_GIST_ID}. {res.status_code} - {res.text}")
            # If Gist is deleted (404), create a new one
            if res.status_code == 404:
                app_logger.error("DB: Gist 404! Recreating Gist...")
                _create_gist(files_dict.get('bot_state.json', {}).get('content', '{}'),
                             files_dict.get('active_positions.json', {}).get('content', '{}'))
    except Exception as e:
        app_logger.error(f"DB: Exception updating Gist: {e}")
    return False

def _fetch_gist_file(filename):
    """Fetches a specific file from the Gist."""
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
            else:
                return {} # File doesn't exist yet
        elif res.status_code == 404:
            app_logger.error("DB: Gist 404! Needs recreation on next save.")
            return None
    except Exception as e:
        app_logger.error(f"DB: Exception fetching Gist {filename}: {e}")
    return None

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
    if not GITHUB_PAT:
        app_logger.error("DB: GITHUB_PAT missing! Operating in LOCAL ONLY mode.")
        return
        
    if not GITHUB_GIST_ID:
        app_logger.warning("DB: GITHUB_GIST_ID missing. Will create a new Gist on first save.")
    else:
        app_logger.info(f"DB: Connected to GitHub Gist: ...{GITHUB_GIST_ID[-8:]}")
    _connected = True

# ---------------------------------------------------------
# Public API
# ---------------------------------------------------------

def load_all_data() -> dict:
    """Loads trade_history, daily_reports, and bot_state from Gist."""
    with _sync_lock:
        if not _connected: _connect()
        
        # 1. Try Cloud
        data = _fetch_gist_file("bot_state.json")
        if data is not None:
            # Overwrite local fallback files so they stay in sync
            try:
                with open(BOT_STATE_FILE, 'w') as f: json.dump(data, f, indent=4)
            except: pass
            
            # The bot engine expects 'trades' directly inside the unified dictionary
            if 'trade_history' in data and 'trades' not in data:
                data['trades'] = data.pop('trade_history')
            return data
            
        # 2. Fallback to Local
        app_logger.warning("DB: Cloud load failed. Falling back to local files.")
        local_data = {}
        
        # Try to gather from local split files
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
                    
            # Auto-create Gist if missing and we have PAT
            if GITHUB_PAT and not GITHUB_GIST_ID:
                app_logger.info("DB: Bootstrapping new Gist from local data...")
                content_str = json.dumps(local_data, indent=4)
                _create_gist(content_str, "{}")
                    
            return local_data
        except Exception as e:
            app_logger.error(f"DB: Local load failed: {e}")
            return {}

def save_all_data(trade_data: dict) -> bool:
    """Saves unified state to Gist."""
    with _sync_lock:
        if not _connected: _connect()
        
        # Unify into bot_state.json structure
        unified = {
            "trade_history": trade_data.get("trades", []),
            "daily_reports": trade_data.get("daily_reports", []),
            "state": trade_data.get("state", {})
        }
        content_str = json.dumps(unified, indent=4)
        
        # Save local fallback
        try:
            with open(BOT_STATE_FILE, 'w') as f: f.write(content_str)
            with open("trade_history.json", 'w') as f: json.dump({"trades": unified["trade_history"]}, f, indent=4)
            with open("daily_reports.json", 'w') as f: json.dump({"reports": unified["daily_reports"]}, f, indent=4)
        except Exception as e:
            app_logger.error(f"DB: Local save failed: {e}")
            
        if not GITHUB_PAT:
            return False
            
        if not GITHUB_GIST_ID:
            _create_gist(content_str, "{}")
            return True
            
        # Update existing Gist
        return _update_gist({"bot_state.json": {"content": content_str}})

def load_active_positions() -> dict:
    """Loads active positions from Gist."""
    with _sync_lock:
        if not _connected: _connect()
        data = _fetch_gist_file("active_positions.json")
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
    """Saves active positions to Gist."""
    with _sync_lock:
        if not _connected: _connect()
        content_str = json.dumps(positions, indent=4)
        
        try:
            with open(ACTIVE_POS_FILE, 'w') as f: f.write(content_str)
        except:
            pass
            
        if not GITHUB_PAT: return
        
        if not GITHUB_GIST_ID:
            _create_gist("{}", content_str)
            return
            
        _update_gist({"active_positions.json": {"content": content_str}})

def trigger_cloud_sync():
    app_logger.info("DB: Manual Cloud Sync Triggered (Gist)")

def is_connected() -> bool:
    return bool(GITHUB_GIST_ID and GITHUB_PAT)

def save_backup_data(data: dict) -> bool:
    """Saves a backup copy of the state to the Gist."""
    with _sync_lock:
        if not _connected: _connect()
        try:
            content = json.dumps(data, indent=4)
            return _update_gist({"backup_state.json": {"content": content}})
        except Exception as e:
            app_logger.error(f"DB: Failed to save backup: {e}")
            return False

def load_backup_data() -> dict:
    """Loads the backup copy from the Gist."""
    with _sync_lock:
        if not _connected: _connect()
        try:
            data = _fetch_gist_file("backup_state.json")
            return data if data else {}
        except Exception as e:
            app_logger.error(f"DB: Failed to load backup: {e}")
            return {}
