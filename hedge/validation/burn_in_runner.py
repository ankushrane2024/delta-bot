import logging
import time
import json
import os
from typing import Dict, Any

from hedge.deployment.service_runner import ServiceRunner

logger = logging.getLogger("system")

class BurnInRunner:
    """
    Executes continuous runs (24h, 72h, 7d) and triggers hourly summaries.
    Validates stable operation during extended execution.
    """
    def __init__(self, duration_hours: int, runner: ServiceRunner):
        self.duration_hours = duration_hours
        self.runner = runner
        self.start_time = time.time()
        self.last_summary_time = self.start_time

    def run(self):
        logger.info(f"Starting {self.duration_hours}-hour Burn-In Validation...")
        
        # We start the ServiceRunner in a background thread or manage it here
        # Since ServiceRunner blocks in a while loop, we will wrap its loop logic
        # or replace the running condition. 
        # But wait, ServiceRunner handles the master loop. We shouldn't modify it.
        # Instead, BurnInRunner can run alongside as a daemon, OR we just let it
        # wake up every hour to generate reports, then signal ServiceRunner to stop.
        
        import threading
        
        def watchdog():
            while self.runner.running:
                now = time.time()
                elapsed_hours = (now - self.start_time) / 3600.0
                
                if elapsed_hours >= self.duration_hours:
                    logger.info(f"Burn-In completed successfully after {self.duration_hours} hours.")
                    self.runner.shutdown()
                    break
                    
                # Generate summary every hour
                if (now - self.last_summary_time) >= 3600.0:
                    self.generate_summary("hourly")
                    self.last_summary_time = now
                    
                time.sleep(10)
                
        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        
        # Start ServiceRunner
        # ServiceRunner needs to be initialized. 
        # In a real environment, BurnInRunner is called *by* a script that initializes ServiceRunner.
        watchdog_thread.start()
        self.runner.run()
        
    def generate_summary(self, period: str):
        stats = self.runner.analytics.get_live_stats()
        summary = {
            "period": period,
            "uptime_hours": (time.time() - self.start_time) / 3600.0,
            "total_ticks": stats.get("total_ticks", 0),
            "total_fills": stats.get("total_fills", 0),
            "average_latency_ms": stats.get("average_latency_ms", 0.0),
            "circuit_breaker_hits": stats.get("circuit_breaker_hits", 0)
        }
        
        filename = f"burnin_summary.json"
        with open(filename, "w") as f:
            json.dump(summary, f, indent=4)
            
        with open("burnin_summary.html", "w") as f:
            f.write(f"<html><body><h1>Burn-In Summary ({period})</h1><pre>{json.dumps(summary, indent=4)}</pre></body></html>")
            
        logger.info(f"Generated {period} burn-in summary.")
