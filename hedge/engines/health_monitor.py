import time

class HealthMonitor:
    def __init__(self, clock=None):
        self.clock = clock
        self.last_ws_msg_time = 0.0
        self.last_sync_time = 0.0
        self.consecutive_errors = 0
        
    def _now(self):
        if self.clock:
            return self.clock.now()
        return time.time()
        
    def mark_ws_msg(self):
        self.last_ws_msg_time = self._now()
        
    def mark_sync(self):
        self.last_sync_time = self._now()
        
    def record_error(self):
        self.consecutive_errors += 1
        
    def reset_errors(self):
        self.consecutive_errors = 0
        
    def get_health(self) -> str:
        now = self._now()
        ws_age = now - self.last_ws_msg_time
        sync_age = now - self.last_sync_time
        
        # If no messages ever received, assume initializing
        if self.last_ws_msg_time == 0.0:
            return "YELLOW"
            
        if self.consecutive_errors > 5 or ws_age > 10.0 or sync_age > 300.0:
            return "RED"
            
        if self.consecutive_errors > 0 or ws_age > 2.0 or sync_age > 60.0:
            return "YELLOW"
            
        return "GREEN"
