import unittest
import os
import json
from unittest.mock import Mock

from hedge.models.tick import TickResult
from hedge.models.events import EventBus, OrderSubmitted, ExecutionOrder
from hedge.validation.validation_engine import ValidationEngine
from hedge.validation.shadow_analytics import ShadowAnalytics
from hedge.engines.shadow.shadow_store import ShadowStore
from hedge.validation.validation_reporter import ValidationReporter

class TestShadowFramework(unittest.TestCase):
    
    def setUp(self):
        import uuid
        self.db_path = f"test_shadow_{uuid.uuid4()}.db"
        self.store = ShadowStore(self.db_path)
        self.analytics = ShadowAnalytics()
        self.event_bus = EventBus()
        self.engine = ValidationEngine(self.event_bus, self.store, self.analytics)
        
    def tearDown(self):
        self.store.close()
        import time
        time.sleep(0.2) # let thread close
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except Exception:
            pass
        if os.path.exists("daily_summary.json"):
            os.remove("daily_summary.json")
        if os.path.exists("daily_summary.html"):
            os.remove("daily_summary.html")
            
    def test_validation_engine_no_mutation(self):
        tick = TickResult(
            timestamp=100.0,
            tick_number=1,
            pipeline_latency=0.01
        )
        self.engine.observe_tick(tick)
        
        # Verify it went to analytics
        stats = self.analytics.get_live_stats()
        self.assertEqual(stats["total_ticks"], 1)
        
    def test_shadow_analytics(self):
        tick = TickResult(timestamp=100.0, tick_number=1, pipeline_latency=0.01)
        self.analytics.on_tick_result(tick)
        
        tick2 = TickResult(timestamp=101.0, tick_number=2, pipeline_latency=0.02)
        self.analytics.on_tick_result(tick2)
        
        stats = self.analytics.get_live_stats()
        self.assertEqual(stats["total_ticks"], 2)
        self.assertEqual(stats["average_latency_ms"], 15.0) # (0.01 + 0.02) / 2 * 1000
        
    def test_validation_reports(self):
        # We need to give the store a tiny bit of time to flush the queue
        import time
        tick = TickResult(timestamp=100.0, tick_number=1, pipeline_latency=0.01)
        self.store.log_tick_result(tick)
        time.sleep(0.1) # allow worker thread to process
        
        reporter = ValidationReporter(self.db_path)
        summary = reporter.generate_daily_summary()
        self.assertEqual(summary["total_ticks_processed"], 1)
        self.assertTrue(os.path.exists("daily_summary.json"))
        
if __name__ == '__main__':
    unittest.main()
