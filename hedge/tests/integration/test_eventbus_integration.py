import unittest
import threading
import time
from typing import List, Any
from hedge.models.events import EventBus
from hedge.models.execution import ExecutionOrder, ExecutionState
from hedge.models.hedge import HedgePlan
from hedge.models.core_interfaces import SystemClock

class TestEvent(object):
    def __init__(self, name):
        self.name = name

class TestEventBusIntegration(unittest.TestCase):
    
    def setUp(self):
        self.bus = EventBus()
        self.clock = SystemClock()
        
    def test_event_ordering(self):
        """Verifies exact event order and no lost/duplicate events."""
        received = []
        
        def handler(event):
            received.append(event.name)
            
        self.bus.subscribe(TestEvent, handler)
        
        # Publish exactly 100 events
        for i in range(100):
            self.bus.publish(TestEvent(f"evt_{i}"))
            
        self.assertEqual(len(received), 100, "Lost or duplicate events detected")
        for i in range(100):
            self.assertEqual(received[i], f"evt_{i}", f"Ordering failed at {i}")
            
    def test_concurrency_stress(self):
        """Verifies thread-safety of publisher and subscriber registry."""
        received_thread_1 = []
        received_thread_2 = []
        
        def handler1(event):
            received_thread_1.append(event.name)
            
        def handler2(event):
            received_thread_2.append(event.name)
            
        self.bus.subscribe(TestEvent, handler1)
        self.bus.subscribe(TestEvent, handler2)
        
        def publisher(thread_id, count):
            for i in range(count):
                self.bus.publish(TestEvent(f"t{thread_id}_{i}"))
                time.sleep(0.0001)  # small jitter
                
        t1 = threading.Thread(target=publisher, args=(1, 500))
        t2 = threading.Thread(target=publisher, args=(2, 500))
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # We expect exact counts
        self.assertEqual(len(received_thread_1), 1000)
        self.assertEqual(len(received_thread_2), 1000)
        
        # We also expect that both threads received exactly the same events
        self.assertEqual(set(received_thread_1), set(received_thread_2))
        
        # Verify no duplicates within a handler
        self.assertEqual(len(set(received_thread_1)), 1000)

if __name__ == '__main__':
    unittest.main()
