import threading
import time
from hedge.models.core_interfaces import Clock

class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter to prevent HTTP 429s.
    """
    def __init__(self, clock: Clock, requests_per_second: float):
        self.clock = clock
        self.capacity = requests_per_second
        self.tokens = self.capacity
        self.last_refill = self.clock.now()
        self.lock = threading.RLock()
        self.fill_rate = requests_per_second

    def _refill(self):
        now = self.clock.now()
        dt = now - self.last_refill
        if dt > 0:
            self.tokens = min(self.capacity, self.tokens + dt * self.fill_rate)
            self.last_refill = now

    def acquire(self):
        while True:
            with self.lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                # Calculate sleep time needed to get 1 token
                sleep_time = (1.0 - self.tokens) / self.fill_rate
            
            # Sleep outside the lock so other threads can do things
            time.sleep(sleep_time)
