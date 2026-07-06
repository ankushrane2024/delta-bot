import logging
import os
import threading
from typing import Dict, Any

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger("system")

class ResourceMonitor:
    """
    Tracks OS-level and application resource usage.
    Detects memory leaks and thread leaks.
    """
    def __init__(self, db_path: str = "shadow_validation.db", log_dir: str = "logs"):
        self.db_path = db_path
        self.log_dir = log_dir
        self.process = psutil.Process(os.getpid()) if psutil else None
        
        # Track for leak detection
        self.initial_memory = self.process.memory_info().rss if self.process else 0
        self.initial_threads = threading.active_count()

    def get_statistics(self) -> Dict[str, Any]:
        if not self.process:
            return {"error": "psutil not installed"}
            
        mem_info = self.process.memory_info()
        current_memory = mem_info.rss
        memory_growth = current_memory - self.initial_memory
        
        current_threads = threading.active_count()
        thread_growth = current_threads - self.initial_threads
        
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        
        return {
            "cpu_percent": self.process.cpu_percent(),
            "ram_mb": current_memory / (1024 * 1024),
            "memory_growth_mb": memory_growth / (1024 * 1024),
            "thread_count": current_threads,
            "thread_growth": thread_growth,
            "open_file_handles": len(self.process.open_files()) if hasattr(self.process, 'open_files') else 0,
            "sqlite_size_mb": db_size / (1024 * 1024)
        }

    def detect_leaks(self) -> List[str]:
        warnings = []
        stats = self.get_statistics()
        if "error" in stats: return warnings
        
        if stats["memory_growth_mb"] > 500:
            warnings.append(f"Severe Memory Leak detected: +{stats['memory_growth_mb']:.2f} MB")
        if stats["thread_growth"] > 50:
            warnings.append(f"Thread Leak detected: +{stats['thread_growth']} threads")
            
        return warnings
