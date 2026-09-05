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

_MASTER_JSONBLOB_ID = "019f94b6-d3ab-7401-83c2-807c661984c0"
JSONBLOB_ID = None

# Local files for fallback and caching
BOT_STATE_FILE = "bot_state.json"
ACTIVE_POS_FILE = "active_positions.json"
LIVE_ACTIVE_POS_FILE = "live_active_positions.json"
API_CREDENTIALS_FILE = "api_credentials.json"
CONFIG_FILE = "cloud_db_config.json"
_LAST_BACKUP_TIME_FILE = ".last_backup_time"

_connected = False
_sync_lock = threading.RLock()

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
            
    # CRITICAL: Auto-discover GITHUB_GIST_ID to survive Render wipes
    if GITHUB_PAT and not GITHUB_GIST_ID:
        try:
            res = requests.get("https://api.github.com/gists", headers=_get_headers(), timeout=5)
            if res.status_code == 200:
                for gist in res.json():
                    if gist.get("description") == "Delta BTC Options Bot - Master DB":
                        GITHUB_GIST_ID = gist.get("id")
                        app_logger.info(f"DB: Auto-discovered Master Gist from GitHub: ...{GITHUB_GIST_ID[-8:]}")
                        break
        except Exception as e:
            app_logger.error(f"DB: Failed to auto-discover Gist: {e}")
            
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
    # If file was wiped by Render, try to read it from the cloud memory
    try:
        cloud_data = load_all_data() or {}
        if "last_backup_time" in cloud_data:
            return cloud_data["last_backup_time"]
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
            if 'live_trade_history' in data and 'live_trades' not in data:
                data['live_trades'] = data.pop('live_trade_history')
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

            if os.path.exists("live_trade_history.json"):
                with open("live_trade_history.json", 'r') as f:
                    lh = json.load(f)
                    local_data['live_trades'] = lh.get("trades", [])
                    local_data['live_max_equity'] = lh.get("max_equity", 0.0)
            elif os.path.exists(BOT_STATE_FILE):
                 with open(BOT_STATE_FILE, 'r') as f:
                    bs = json.load(f)
                    local_data['live_trades'] = bs.get("live_trade_history", [])
                    local_data['live_max_equity'] = bs.get("live_max_equity", 0.0)
                    
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
        
        # --- VAULT PROTECTION: Prevent accidental wipe of history ---
        existing_data = load_all_data() or {}
        old_paper = existing_data.get("trades", existing_data.get("trade_history", []))
        new_paper = trade_data.get("trades", [])
        old_live = existing_data.get("live_trades", existing_data.get("live_trade_history", []))
        new_live = trade_data.get("live_trades", [])
        
        if len(new_paper) < len(old_paper):
            app_logger.error(f"VAULT PROTECTION: Attempt to shrink paper trades from {len(old_paper)} to {len(new_paper)} blocked. Forcing merge.")
            trade_data["trades"] = old_paper + [t for t in new_paper if t not in old_paper]
            
        if len(new_live) < len(old_live):
            app_logger.error(f"VAULT PROTECTION: Attempt to shrink live trades from {len(old_live)} to {len(new_live)} blocked. Forcing merge.")
            trade_data["live_trades"] = old_live + [t for t in new_live if t not in old_live]
        # -----------------------------------------------------------
        
        now_str = get_ist_now().strftime("%d %b, %H:%M IST")
        unified = {
            "max_equity": trade_data.get("max_equity", 0.0),
            "trade_history": trade_data.get("trades", []),
            "live_max_equity": trade_data.get("live_max_equity", 0.0),
            "live_trade_history": trade_data.get("live_trades", []),
            "daily_reports": trade_data.get("daily_reports", []),
            "state": trade_data.get("state", {}),
            "last_backup_time": now_str
        }
        
        # Save local fallback
        try:
            with open(BOT_STATE_FILE, 'w') as f: json.dump(unified, f, indent=4)
            with open("trade_history.json", 'w') as f: json.dump({"trades": unified["trade_history"], "max_equity": unified["max_equity"]}, f, indent=4)
            with open("live_trade_history.json", 'w') as f: json.dump({"trades": unified["live_trade_history"], "max_equity": unified["live_max_equity"]}, f, indent=4)
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
               return _update_jsonblob(blob_data)

def load_live_active_positions() -> dict:
    """Loads live active options positions from Cloud or local fallback."""
    with _sync_lock:
        if not _connected: _connect()
        data = None
        if GITHUB_PAT and GITHUB_GIST_ID:
            data = _fetch_gist_file("live_active_positions.json")
        elif JSONBLOB_ID:
            blob_data = _fetch_jsonblob()
            if blob_data:
                data = blob_data.get("live_active_positions", {})
                
        if data is not None:
            return data
            
        if os.path.exists(LIVE_ACTIVE_POS_FILE):
            try:
                with open(LIVE_ACTIVE_POS_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

def save_live_active_positions(positions: dict):
    """Saves live active positions to Cloud and local fallback."""
    with _sync_lock:
        if not _connected: _connect()
        content_str = json.dumps(positions, indent=4)
        
        try:
            with open(LIVE_ACTIVE_POS_FILE, 'w') as f: f.write(content_str)
        except:
            pass
            
        if GITHUB_PAT:
            if not GITHUB_GIST_ID:
                _create_gist("{}", content_str)
            else:
                _update_gist({"live_active_positions.json": {"content": content_str}})
        else:
            blob_data = _fetch_jsonblob() or {}
            blob_data["live_active_positions"] = positions
            if not JSONBLOB_ID:
                _create_jsonblob(blob_data)
            else:
               return _update_jsonblob(blob_data)

def load_audit_log() -> list:
    """Loads the active decision audit session from Cloud."""
    with _sync_lock:
        if not _connected: _connect()
        
        # Local fallback
        local_audit = []
        if os.path.exists("decision_audit.json"):
            try:
                with open("decision_audit.json", 'r') as f:
                    local_audit = json.load(f)
            except:
                pass
                
        if GITHUB_PAT:
            if not GITHUB_GIST_ID: return local_audit
            content = _fetch_gist_file("decision_audit.json")
            if content:
                try:
                    return json.loads(content)
                except:
                    return local_audit
            return local_audit
        else:
            blob_data = _fetch_jsonblob()
            if blob_data and "decision_audit" in blob_data:
                return blob_data["decision_audit"]
            return local_audit

def save_audit_log(events: list) -> bool:
    """Saves the decision audit session to Cloud."""
    with _sync_lock:
        if not _connected: _connect()
        
        try:
            with open("decision_audit.json", 'w') as f:
                json.dump(events, f, indent=4)
        except Exception as e:
            app_logger.error(f"DB: Local audit save failed: {e}")
            
        if GITHUB_PAT:
            content_str = json.dumps(events, indent=4)
            if not GITHUB_GIST_ID:
                _create_gist("{}", "{}")  # create empty
            return _update_gist({"decision_audit.json": {"content": content_str}})
        else:
            blob_data = _fetch_jsonblob() or {}
            blob_data["decision_audit"] = events
            if not JSONBLOB_ID:
                _create_jsonblob(blob_data)
                return True
            return _update_jsonblob(blob_data)

def save_trade_entry_receipt(entry_data: dict) -> bool:
    """
    DEPLOY-SAFE GUARD: Saves a 'trade open' receipt to cloud IMMEDIATELY when a trade is entered.
    
    This solves the problem where Render redeploys mid-trade wipe the in-memory trade entry
    data before log_trade() is called on close. On restart, load_trade_entry_receipt() recovers
    this record so the trade can be reconstructed in history.
    
    Called by: bot_engine.py immediately after execute_strangle() succeeds.
    Cleared by: performance_tracker.py after log_trade() completes successfully.
    
    entry_data keys: date, mode, entry_time, call_symbol, put_symbol,
                     call_entry_price, put_entry_price, premium_collected, btc_entry_price
    """
    with _sync_lock:
        if not _connected: _connect()
        receipt = dict(entry_data)
        receipt["_receipt_type"] = "OPEN_TRADE"
        receipt["_saved_at"] = get_ist_now().isoformat()
        
        # Save locally always
        try:
            with open("open_trade_receipt.json", 'w') as f:
                json.dump(receipt, f, indent=4)
        except Exception as e:
            app_logger.error(f"DB: Failed to save open_trade_receipt locally: {e}")
        
        # Save to cloud
        try:
            if GITHUB_PAT:
                if GITHUB_GIST_ID:
                    return _update_gist({"open_trade_receipt.json": {"content": json.dumps(receipt, indent=4)}})
            else:
                blob_data = _fetch_jsonblob() or {}
                blob_data["open_trade_receipt"] = receipt
                if not JSONBLOB_ID:
                    _create_jsonblob(blob_data)
                    return True
                return _update_jsonblob(blob_data)
        except Exception as e:
            app_logger.error(f"DB: Failed to save open_trade_receipt to cloud: {e}")
        return False

def load_trade_entry_receipt() -> dict:
    """
    Loads the open trade receipt saved by save_trade_entry_receipt().
    Returns the receipt dict if a trade was open before restart, or {} if none.
    Called on bot startup to detect and recover mid-trade restarts.
    """
    with _sync_lock:
        if not _connected: _connect()
        
        # Try cloud first
        try:
            if GITHUB_PAT and GITHUB_GIST_ID:
                data = _fetch_gist_file("open_trade_receipt.json")
                if data:
                    return json.loads(data) if isinstance(data, str) else data
            elif JSONBLOB_ID:
                blob_data = _fetch_jsonblob()
                if blob_data and "open_trade_receipt" in blob_data:
                    return blob_data["open_trade_receipt"]
        except Exception as e:
            app_logger.warning(f"DB: Cloud receipt load failed: {e}")
        
        # Fallback to local
        if os.path.exists("open_trade_receipt.json"):
            try:
                with open("open_trade_receipt.json", 'r') as f:
                    return json.load(f)
            except Exception as e:
                app_logger.warning(f"DB: Local receipt load failed: {e}")
        return {}

def clear_trade_entry_receipt() -> bool:
    """
    Clears the open trade receipt after log_trade() completes successfully.
    Called by performance_tracker.py after a trade is fully recorded.
    """
    with _sync_lock:
        # Clear local
        try:
            if os.path.exists("open_trade_receipt.json"):
                os.remove("open_trade_receipt.json")
        except Exception:
            pass
        
        # Clear from cloud
        try:
            if GITHUB_PAT and GITHUB_GIST_ID:
                _update_gist({"open_trade_receipt.json": {"content": "{}"}})
            elif JSONBLOB_ID:
                blob_data = _fetch_jsonblob() or {}
                blob_data.pop("open_trade_receipt", None)
                _update_jsonblob(blob_data)
        except Exception as e:
            app_logger.warning(f"DB: Failed to clear receipt from cloud: {e}")
        return True

def trigger_cloud_sync():
    app_logger.info("DB: Manual Cloud Sync Triggered")

def is_connected() -> bool:
    return True # We now always have a connection (either Gist or JSONBlob fallback)


def load_all_api_credentials() -> dict:
    """
    Loads full persistent Delta Exchange API credentials from Cloud or local fallback.
    Supports dual-slots: 'live' and 'demo' accounts.
    Survives Render container reboots and redeploys.
    """
    with _sync_lock:
        if not _connected: _connect()
        creds = None
        try:
            if GITHUB_PAT and GITHUB_GIST_ID:
                content = _fetch_gist_file("api_credentials.json")
                if content:
                    creds = json.loads(content)
            elif JSONBLOB_ID:
                blob_data = _fetch_jsonblob()
                if blob_data:
                    creds = blob_data.get("api_credentials", None)
        except Exception as _e:
            app_logger.warning(f"DB: Cloud load for api_credentials failed: {_e}")

        # Fallback to local file if cloud load was empty
        if not creds and os.path.exists(API_CREDENTIALS_FILE):
            try:
                with open(API_CREDENTIALS_FILE, 'r', encoding='utf-8') as f:
                    creds = json.load(f)
            except Exception:
                pass

        normalized = {
            "live": {
                "api_key": "",
                "api_secret": "",
                "environment": "india_live",
                "base_url": "https://api.india.delta.exchange",
                "profile": {}
            },
            "demo": {
                "api_key": "",
                "api_secret": "",
                "environment": "demo",
                "base_url": "https://testnet-api.delta.exchange",
                "profile": {}
            },
            "active_slot": "live",
            "api_key": "",
            "api_secret": ""
        }

        if creds and isinstance(creds, dict):
            # Check if old format {"api_key": "...", "api_secret": "..."}
            if "live" in creds or "demo" in creds:
                if isinstance(creds.get("live"), dict):
                    normalized["live"].update(creds["live"])
                if isinstance(creds.get("demo"), dict):
                    normalized["demo"].update(creds["demo"])
                normalized["active_slot"] = creds.get("active_slot", "live")
            else:
                # Old single-key format: migrate to live slot
                old_k = creds.get("api_key", "").strip()
                old_s = creds.get("api_secret", "").strip()
                if old_k and old_s:
                    normalized["live"]["api_key"] = old_k
                    normalized["live"]["api_secret"] = old_s

            act = normalized["active_slot"]
            act_data = normalized.get(act, normalized["live"])
            normalized["api_key"] = act_data.get("api_key", "")
            normalized["api_secret"] = act_data.get("api_secret", "")

        # Fallback to environment variables if slots are empty
        if not normalized["live"]["api_key"]:
            env_live_k = (os.getenv("DELTA_API_KEY") or getattr(config, 'DELTA_API_KEY', '') or '').strip()
            env_live_s = (os.getenv("DELTA_API_SECRET") or getattr(config, 'DELTA_API_SECRET', '') or '').strip()
            if env_live_k and env_live_s and env_live_k not in ('testnet_key', 'YOUR_KEY_HERE', ''):
                normalized["live"]["api_key"] = env_live_k
                normalized["live"]["api_secret"] = env_live_s
                normalized["live"]["environment"] = "india_live"
                normalized["live"]["base_url"] = getattr(config, 'DELTA_INDIA_BASE_URL', "https://api.india.delta.exchange")

        if not normalized["demo"]["api_key"]:
            env_demo_k = (os.getenv("DELTA_DEMO_API_KEY") or '').strip()
            env_demo_s = (os.getenv("DELTA_DEMO_API_SECRET") or '').strip()
            if env_demo_k and env_demo_s:
                normalized["demo"]["api_key"] = env_demo_k
                normalized["demo"]["api_secret"] = env_demo_s
                normalized["demo"]["environment"] = "demo"
                normalized["demo"]["base_url"] = getattr(config, 'DELTA_GLOBAL_DEMO_BASE_URL', "https://testnet-api.delta.exchange")

        act = normalized.get("active_slot", "live")
        act_data = normalized.get(act, normalized["live"])
        normalized["api_key"] = act_data.get("api_key", "")
        normalized["api_secret"] = act_data.get("api_secret", "")

        # If local cache file doesn't exist, write it so it persists locally
        if not os.path.exists(API_CREDENTIALS_FILE) and (normalized["live"]["api_key"] or normalized["demo"]["api_key"]):
            try:
                with open(API_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(normalized, f, indent=4)
            except Exception:
                pass

        return normalized


def load_api_credentials() -> tuple:
    """
    Loads active Delta Exchange API credentials from Cloud or local fallback.
    Returns (api_key, api_secret).
    Survives Render container reboots and redeploys.
    """
    all_creds = load_all_api_credentials()
    act = all_creds.get("active_slot", "live")
    act_data = all_creds.get(act, all_creds.get("live", {}))
    k = act_data.get("api_key", "").strip()
    s = act_data.get("api_secret", "").strip()
    if k and s:
        return k, s
    # Fallback to live slot if active is empty
    live_data = all_creds.get("live", {})
    return live_data.get("api_key", "").strip(), live_data.get("api_secret", "").strip()


def get_active_api_slot() -> str:
    all_creds = load_all_api_credentials()
    return all_creds.get("active_slot", "live")


def set_active_api_slot(slot: str) -> tuple:
    """
    Switches the active API slot ('live' or 'demo').
    Returns (success, slot_dict).
    """
    with _sync_lock:
        all_creds = load_all_api_credentials()
        slot = slot.lower()
        if slot not in ("live", "demo"):
            return False, {}
        slot_data = all_creds.get(slot, {})
        if not slot_data.get("api_key"):
            app_logger.warning(f"DB: Cannot switch to {slot.upper()} - slot has no configured API key.")
            return False, slot_data
        all_creds["active_slot"] = slot
        all_creds["api_key"] = slot_data.get("api_key", "")
        all_creds["api_secret"] = slot_data.get("api_secret", "")
        _persist_credentials_dict(all_creds)
        app_logger.info(f"DB: Switched active API slot to {slot.upper()}")
        return True, slot_data


def save_api_credentials(api_key: str, api_secret: str, slot: str = "live",
                         environment: str = None, base_url: str = None,
                         profile: dict = None) -> bool:
    """
    Permanently saves Delta Exchange API credentials for a specific slot ('live' or 'demo')
    to Cloud (survives Render redeploys) and local fallback.
    """
    with _sync_lock:
        if not _connected: _connect()
        all_creds = load_all_api_credentials()
        slot = slot.lower() if slot in ("live", "demo") else "live"
        
        slot_dict = all_creds.get(slot, {})
        slot_dict["api_key"] = api_key.strip()
        slot_dict["api_secret"] = api_secret.strip()
        if environment: slot_dict["environment"] = environment
        if base_url: slot_dict["base_url"] = base_url.rstrip('/')
        if profile: slot_dict["profile"] = profile
        all_creds[slot] = slot_dict

        # If this slot is active or active is currently empty, update active pointer
        if all_creds.get("active_slot") == slot or not all_creds.get("api_key"):
            all_creds["active_slot"] = slot
            all_creds["api_key"] = api_key.strip()
            all_creds["api_secret"] = api_secret.strip()

        return _persist_credentials_dict(all_creds)


def disable_api_slot(slot: str = "active") -> bool:
    """
    Disables API credentials for a given slot ('live', 'demo', 'active', or 'all').
    """
    with _sync_lock:
        all_creds = load_all_api_credentials()
        target = slot.lower()
        if target == "all":
            all_creds["live"]["api_key"] = ""
            all_creds["live"]["api_secret"] = ""
            all_creds["live"]["profile"] = {}
            all_creds["demo"]["api_key"] = ""
            all_creds["demo"]["api_secret"] = ""
            all_creds["demo"]["profile"] = {}
            all_creds["api_key"] = ""
            all_creds["api_secret"] = ""
        elif target in ("live", "demo"):
            all_creds[target]["api_key"] = ""
            all_creds[target]["api_secret"] = ""
            all_creds[target]["profile"] = {}
            if all_creds.get("active_slot") == target:
                all_creds["api_key"] = ""
                all_creds["api_secret"] = ""
        else: # "active"
            act = all_creds.get("active_slot", "live")
            all_creds[act]["api_key"] = ""
            all_creds[act]["api_secret"] = ""
            all_creds[act]["profile"] = {}
            all_creds["api_key"] = ""
            all_creds["api_secret"] = ""

        return _persist_credentials_dict(all_creds)


def _persist_credentials_dict(all_creds: dict) -> bool:
    content_str = json.dumps(all_creds, indent=4)
    try:
        with open(API_CREDENTIALS_FILE, 'w', encoding='utf-8') as f:
            f.write(content_str)
    except Exception:
        pass

    try:
        if GITHUB_PAT:
            if not GITHUB_GIST_ID:
                _create_gist("{}", content_str)
            else:
                _update_gist({"api_credentials.json": {"content": content_str}})
            app_logger.info("DB: API credentials saved permanently to GitHub Gist.")
            return True
        else:
            blob_data = _fetch_jsonblob() or {}
            blob_data["api_credentials"] = all_creds
            if not JSONBLOB_ID:
                _create_jsonblob(blob_data)
            else:
                _update_jsonblob(blob_data)
            app_logger.info("DB: API credentials saved permanently to Cloud Master DB.")
            return True
    except Exception as e:
        app_logger.error(f"DB: Failed to save api_credentials to Cloud: {e}")
        return False

