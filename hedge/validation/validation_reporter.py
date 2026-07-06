import json
import sqlite3
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ValidationReporter:
    """
    Generates daily summaries and validation reports (HTML/JSON).
    Queries SQLite store directly to avoid blocking memory views.
    """
    
    def __init__(self, db_path: str = "shadow_validation.db"):
        self.db_path = db_path
        
    def generate_daily_summary(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            c.execute("SELECT COUNT(*) as cnt FROM tick_results")
            total_ticks = c.fetchone()["cnt"]
            
            c.execute("SELECT COUNT(*) as cnt FROM tick_results WHERE decision_action != 'HOLD'")
            total_actions = c.fetchone()["cnt"]
            
            c.execute("SELECT MAX(risk_score) as max_risk, AVG(latency) as avg_latency FROM tick_results")
            row = c.fetchone()
            max_risk = row["max_risk"] if row["max_risk"] else 0.0
            avg_latency = row["avg_latency"] if row["avg_latency"] else 0.0
            
            c.execute("SELECT COUNT(*) as cnt FROM execution_events WHERE event_type = 'OrderFilled'")
            total_fills = c.fetchone()["cnt"]
            
        summary = {
            "total_ticks_processed": total_ticks,
            "hedge_actions_taken": total_actions,
            "maximum_risk_score_observed": max_risk,
            "average_pipeline_latency": avg_latency,
            "total_simulated_fills": total_fills,
            "overall_status": "SUCCESS" if max_risk < 150 else "WARNING"
        }
        
        with open("daily_summary.json", "w") as f:
            json.dump(summary, f, indent=4)
            
        with open("daily_summary.html", "w") as f:
            f.write(f"<html><body><h1>Daily Summary</h1><pre>{json.dumps(summary, indent=4)}</pre></body></html>")
            
        logger.info("Generated daily_summary.json and daily_summary.html")
        return summary
