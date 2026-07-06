import sqlite3
import threading
import queue
import logging
import json
from typing import Optional

from hedge.models.tick import TickResult
from hedge.models.events import ExecutionEvent

logger = logging.getLogger(__name__)

class ShadowStore:
    """
    Append-only SQLite audit store for Module 38 Shadow Trading Validation.
    Receives validation logs via an asynchronous queue to prevent blocking the hot path.
    """
    def __init__(self, db_path: str = "shadow_validation.db"):
        self.db_path = db_path
        self._write_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = threading.Thread(target=self._writer_loop, daemon=True)
        
        self._init_db()
        self._worker_thread.start()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS tick_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    tick_number INTEGER,
                    schema_version TEXT,
                    tick_hash TEXT,
                    risk_score REAL,
                    decision_action TEXT,
                    decision_reason TEXT,
                    portfolio_delta REAL,
                    latency REAL,
                    raw_json TEXT
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS execution_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    event_type TEXT,
                    order_id TEXT,
                    raw_json TEXT
                )
            ''')
            
            # Indexes for historical dashboard lookups
            c.execute('CREATE INDEX IF NOT EXISTS idx_tick_timestamp ON tick_results(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tick_number ON tick_results(tick_number)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_exec_timestamp ON execution_events(timestamp)')
            
            conn.commit()
            
    def _writer_loop(self):
        """Background thread consuming the queue and writing to SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            while not self._stop_event.is_set() or not self._write_queue.empty():
                try:
                    task = self._write_queue.get(timeout=1.0)
                    task_type, data = task
                    
                    if task_type == "tick":
                        c.execute('''
                            INSERT INTO tick_results 
                            (timestamp, tick_number, schema_version, tick_hash, risk_score, 
                             decision_action, decision_reason, portfolio_delta, latency, raw_json)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', data)
                    elif task_type == "event":
                        c.execute('''
                            INSERT INTO execution_events
                            (timestamp, event_type, order_id, raw_json)
                            VALUES (?, ?, ?, ?)
                        ''', data)
                        
                    conn.commit()
                    self._write_queue.task_done()
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"ShadowStore DB Error: {e}")

    def log_tick_result(self, tick: TickResult):
        risk_score = tick.risk_result.overall_risk_score if tick.risk_result else 0.0
        action = tick.hedge_decision.action.name if tick.hedge_decision else "NONE"
        reason = tick.hedge_decision.reason if tick.hedge_decision else ""
        delta = tick.portfolio_snapshot.net_options_delta if tick.portfolio_snapshot else 0.0
        
        # Serialize fields ignoring non-serializable objects for raw_json audit
        # For a full implementation, a robust JSON encoder handles classes. 
        # Here we just save the hash and primary metrics.
        raw = json.dumps({"tick_hash": tick.tick_hash})
        
        data = (
            tick.timestamp, tick.tick_number, tick.schema_version, tick.tick_hash,
            risk_score, action, reason, delta, tick.pipeline_latency, raw
        )
        self._write_queue.put(("tick", data))
        
    def log_execution_event(self, event: ExecutionEvent):
        order_id = getattr(event, "order", None)
        order_id = order_id.client_order_id if order_id else ""
        
        data = (
            event.timestamp,
            event.__class__.__name__,
            order_id,
            "{}" # Placeholder for robust JSON encoding of event
        )
        self._write_queue.put(("event", data))

    def close(self):
        self._stop_event.set()
        self._worker_thread.join()
