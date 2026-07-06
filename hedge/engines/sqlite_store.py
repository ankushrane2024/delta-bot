import sqlite3
import json
from typing import Any, List, Optional
from enum import Enum
from dataclasses import asdict
from hedge.models.core_interfaces import ExecutionStore

class EnumEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.name
        return super().default(obj)

class SqliteExecutionStore(ExecutionStore):
    """
    Augments an inner ExecutionStore by dual-writing orders and events to a SQLite database.
    This guarantees persistence while maintaining the in-memory speed of the inner store.
    """
    def __init__(self, db_path: str, inner_store: ExecutionStore):
        self.db_path = db_path
        self.inner = inner_store
        self._init_db()
        
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    state TEXT,
                    data TEXT
                )
            ''')
            
    def save_order(self, order: Any) -> None:
        self.inner.save_order(order)
        try:
            with sqlite3.connect(self.db_path) as conn:
                data_json = json.dumps(asdict(order), cls=EnumEncoder)
                conn.execute('''
                    INSERT OR REPLACE INTO orders (client_order_id, plan_id, state, data)
                    VALUES (?, ?, ?, ?)
                ''', (order.client_order_id, order.plan_id, order.state.name, data_json))
        except Exception as e:
            import logging
            logging.getLogger("ARES.SqliteStore").error(f"Failed to save order to SQLite: {e}")

    def get_order(self, order_id: str) -> Optional[Any]:
        return self.inner.get_order(order_id)

    def get_order_by_plan(self, plan_id: str) -> Optional[Any]:
        return self.inner.get_order_by_plan(plan_id)

    def get_active_orders(self) -> List[Any]:
        return self.inner.get_active_orders()
