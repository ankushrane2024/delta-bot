import time
import json
import uuid
import os
from datetime import datetime
import threading
import logging
import traceback
import db_manager

logger = logging.getLogger("AuditCore")
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)

class AuditManager:
    """
    Production-Grade Live Decision Audit System
    Ensures absolute traceability of trading decisions and survival across Render restarts.
    """
    def __init__(self):
        self.current_trade_id = None
        self.session_events = []
        self.pending_sync = []
        self.last_sync_time = time.time()
        self.lock = threading.Lock()
        self.enabled = True
        self.metrics = {
            "sync_latency": [],
            "log_latency": []
        }
        self.last_critical_event = "None"
        
    def start_trade_session(self, btc_price: float):
        """Initializes a new trade audit session."""
        self.current_trade_id = f"BTC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.session_events = []
        self.pending_sync = []
        logger.info(f"Audit: Started new session {self.current_trade_id}")
        self.log_critical_event("Trade Entry", "bot_engine", "run_entry_cycle", 
                                {"BTC Price": btc_price}, "Trade officially started")
        
    def recover_trade_session(self, recovered_events: list):
        """Recovers an existing audit session after a bot restart."""
        with self.lock:
            if recovered_events:
                self.session_events = recovered_events
                self.current_trade_id = recovered_events[0].get("Trade ID")
                logger.warning(f"Audit: Recovered session {self.current_trade_id} with {len(recovered_events)} events.")
            else:
                self.current_trade_id = f"BTC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_RECOVERED_BLANK"
                self.session_events = []
                logger.error("Audit: Recovery triggered but no events found in cloud!")
                
            self.log_critical_event("Hot Recovery", "bot_engine", "_monitor_loop", 
                                    {"Recovered Events": len(self.session_events)}, "Render server restarted and state was recovered")
    
    def log_event(self, event_type: str, module_name: str, function_name: str, 
                  snapshot: dict, reason: str, critical: bool = False, parent_id: str = None):
        """
        Single Source of Truth logging function.
        Records exact runtime values provided in the snapshot.
        """
        if not self.enabled:
            return
            
        start_t = time.perf_counter()
        
        event = {
            "Event ID": str(uuid.uuid4()),
            "Trade ID": self.current_trade_id or "NO_TRADE",
            "Parent Event ID": parent_id,
            "Timestamp": int(time.time() * 1000),
            "Date Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Module Name": module_name,
            "Function Name": function_name,
            "Event Type": event_type,
            "Reason": reason,
            "Snapshot": snapshot
        }
        
        with self.lock:
            self.session_events.append(event)
            self.pending_sync.append(event)
            if critical:
                self.last_critical_event = f"{event_type} at {event['Date Time']}"
                
        latency_ms = (time.perf_counter() - start_t) * 1000
        self.metrics["log_latency"].append(latency_ms)
        if len(self.metrics["log_latency"]) > 100: self.metrics["log_latency"].pop(0)
        
        if critical:
            self.sync_to_cloud(blocking=True)
        else:
            if time.time() - self.last_sync_time > 60:
                self.sync_to_cloud(blocking=False)
                
        return event["Event ID"]
                
    def log_critical_event(self, event_type: str, module_name: str, function_name: str, snapshot: dict, reason: str):
        return self.log_event(event_type, module_name, function_name, snapshot, reason, critical=True)
        
    def log_exception(self, module_name: str, function_name: str, exception: Exception, snapshot: dict):
        snapshot["Exception Type"] = type(exception).__name__
        snapshot["Stack Trace"] = traceback.format_exc()
        self.log_critical_event("Critical Exception", module_name, function_name, snapshot, str(exception))
        
    def sync_to_cloud(self, blocking=False):
        """Syncs the audit batch to JSONBlob to survive Render restarts."""
        with self.lock:
            if not self.pending_sync:
                return
            batch_to_sync = list(self.session_events) # Sync full session state
            self.pending_sync.clear()
            self.last_sync_time = time.time()
            
        def _do_sync():
            start_t = time.perf_counter()
            try:
                db_manager.save_audit_log(batch_to_sync)
            except Exception as e:
                logger.error(f"Audit: Sync failed - {e}")
            latency_ms = (time.perf_counter() - start_t) * 1000
            self.metrics["sync_latency"].append(latency_ms)
            if len(self.metrics["sync_latency"]) > 20: self.metrics["sync_latency"].pop(0)
            
        if blocking:
            _do_sync()
        else:
            threading.Thread(target=_do_sync, daemon=True).start()
            
    def export_session(self):
        """Exports the trade's audit session to a JSON file and clears cloud state."""
        if not self.session_events:
            return None
            
        os.makedirs("exports", exist_ok=True)
        filename = f"exports/audit_{self.current_trade_id}.json"
        
        with self.lock:
            with open(filename, 'w') as f:
                json.dump(self.session_events, f, indent=4)
            self.session_events.clear()
            self.pending_sync.clear()
            self.current_trade_id = None
            
        # Clear cloud state
        db_manager.save_audit_log([])
        logger.info(f"Audit: Session exported to {filename} and cloud state cleared.")
        return filename
        
    def get_dashboard_metrics(self):
        with self.lock:
            avg_log = sum(self.metrics["log_latency"]) / max(1, len(self.metrics["log_latency"]))
            avg_sync = sum(self.metrics["sync_latency"]) / max(1, len(self.metrics["sync_latency"]))
            max_sync = max(self.metrics["sync_latency"]) if self.metrics["sync_latency"] else 0
            
            return {
                "Audit Enabled": "YES" if self.enabled else "NO",
                "Current Trade ID": self.current_trade_id or "None",
                "Events Recorded": len(self.session_events),
                "Pending Queue Size": len(self.pending_sync),
                "Last Sync Time": datetime.fromtimestamp(self.last_sync_time).strftime('%H:%M:%S') if self.session_events else "Never",
                "Last Critical Event": self.last_critical_event,
                "Avg Log Latency (ms)": f"{avg_log:.2f}",
                "Avg Sync Latency (ms)": f"{avg_sync:.0f}",
                "Max Sync Latency (ms)": f"{max_sync:.0f}",
                "Audit Health": "Healthy" if avg_sync < 5000 else "Warning"
            }

audit_system = AuditManager()
