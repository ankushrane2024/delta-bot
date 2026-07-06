import threading
import json
import os
import requests
import logging

logger = logging.getLogger("ARES.ProductCatalog")

class ProductCatalog:
    """
    Downloads and caches Delta Exchange product IDs.
    Thread-safe and persistent.
    """
    def __init__(self, base_url: str, cache_file: str = "product_cache.json"):
        self.base_url = base_url
        self.cache_file = cache_file
        self.lock = threading.RLock()
        
        self.symbol_to_id = {}
        self.id_to_symbol = {}
        
    def load_or_refresh(self, force: bool = False):
        with self.lock:
            if not force and os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r") as f:
                        data = json.load(f)
                        self.symbol_to_id = data.get("symbol_to_id", {})
                        self.id_to_symbol = {int(k): v for k, v in data.get("id_to_symbol", {}).items()}
                    logger.info("Loaded ProductCatalog from cache.")
                    return
                except Exception as e:
                    logger.warning(f"Failed to load product cache: {e}. Refreshing.")
                    
            self._refresh_from_api()
            
    def _refresh_from_api(self):
        try:
            resp = requests.get(f"{self.base_url}/v2/products", timeout=5)
            resp.raise_for_status()
            data = resp.json().get("result", [])
            
            with self.lock:
                self.symbol_to_id.clear()
                self.id_to_symbol.clear()
                for p in data:
                    sym = p.get("symbol", "")
                    pid = p.get("id")
                    if sym and pid:
                        self.symbol_to_id[sym] = pid
                        self.id_to_symbol[pid] = sym
                        
                with open(self.cache_file, "w") as f:
                    json.dump({
                        "symbol_to_id": self.symbol_to_id,
                        "id_to_symbol": self.id_to_symbol
                    }, f)
                logger.info(f"Refreshed ProductCatalog from API. Indexed {len(self.symbol_to_id)} products.")
        except Exception as e:
            logger.error(f"Failed to fetch products from Delta: {e}")
            raise RuntimeError(f"Cannot initialize ProductCatalog: {e}")

    def get_product_id(self, symbol: str) -> int:
        with self.lock:
            if symbol not in self.symbol_to_id:
                raise ValueError(f"Product ID not found for symbol: {symbol}")
            return self.symbol_to_id[symbol]
            
    def get_symbol(self, product_id: int) -> str:
        with self.lock:
            return self.id_to_symbol.get(product_id, str(product_id))
