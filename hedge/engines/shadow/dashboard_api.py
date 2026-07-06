from fastapi import FastAPI, Depends
import sqlite3
from typing import Dict, Any, List

from hedge.validation.shadow_analytics import ShadowAnalytics

# FastAPI application instance
app = FastAPI(title="ARES Shadow Validation Dashboard API")

# In a real app, this would be injected via state or dependency injection.
# For simplicity in this module, we assume it's attached to app.state
# app.state.analytics = ShadowAnalytics()
# app.state.db_path = "shadow_validation.db"

def get_analytics() -> ShadowAnalytics:
    return app.state.analytics

def get_db():
    conn = sqlite3.connect(app.state.db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

@app.get("/health")
def health_check():
    return {"status": "ok", "mode": "shadow_validation"}

@app.get("/dashboard")
def dashboard_live_stats(analytics: ShadowAnalytics = Depends(get_analytics)):
    """Live endpoints read directly from fast, in-memory analytics views to avoid disk I/O."""
    return analytics.get_live_stats()

@app.get("/portfolio")
def portfolio_live(analytics: ShadowAnalytics = Depends(get_analytics)):
    stats = analytics.get_live_stats()
    return {
        "delta": stats.get("current_portfolio_delta", 0.0),
        "daily_pnl": stats.get("daily_pnl", 0.0),
        "realized_pnl": stats.get("realized_pnl", 0.0),
        "unrealized_pnl": stats.get("unrealized_pnl", 0.0),
        "margin_utilization": stats.get("margin_utilization", 0.0)
    }

@app.get("/risk")
def risk_live(analytics: ShadowAnalytics = Depends(get_analytics)):
    stats = analytics.get_live_stats()
    return {
        "max_drawdown": stats.get("max_drawdown", 0.0),
        "circuit_breaker_hits": stats.get("circuit_breaker_hits", 0)
    }

@app.get("/system")
def system_live(analytics: ShadowAnalytics = Depends(get_analytics)):
    stats = analytics.get_live_stats()
    return {
        "average_latency_ms": stats.get("average_latency_ms", 0.0),
        "total_ticks": stats.get("total_ticks", 0)
    }

@app.get("/analytics")
def historical_analytics(db: sqlite3.Connection = Depends(get_db)):
    """Historical endpoints query SQLite."""
    c = db.cursor()
    c.execute("SELECT COUNT(*) as count FROM tick_results")
    row = c.fetchone()
    return {"historical_ticks_recorded": row["count"] if row else 0}

@app.get("/decision")
def historical_decisions(limit: int = 50, db: sqlite3.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute(
        "SELECT tick_number, timestamp, decision_action, decision_reason, risk_score "
        "FROM tick_results "
        "WHERE decision_action != 'HOLD' "
        "ORDER BY tick_number DESC LIMIT ?", (limit,)
    )
    return [dict(row) for row in c.fetchall()]

@app.get("/orders")
def historical_orders(limit: int = 50, db: sqlite3.Connection = Depends(get_db)):
    c = db.cursor()
    c.execute(
        "SELECT timestamp, event_type, order_id "
        "FROM execution_events "
        "ORDER BY id DESC LIMIT ?", (limit,)
    )
    return [dict(row) for row in c.fetchall()]
