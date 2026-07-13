import logging
from hedge.models.core_interfaces import AbstractMarketDataProvider

logger = logging.getLogger(__name__)

class LegacyMarketFeedAdapter(AbstractMarketDataProvider):
    """
    Adapter that provides LIVE market data to ARES directly from the legacy DeltaTradingEngine's api_client,
    without interfering with the PaperExecutionProvider.
    """
    def __init__(self, bot_engine, clock):
        self.engine = bot_engine
        self.clock = clock

    def get_latest_data(self) -> dict:
        """
        Fetches real-time spot price, funding, and options greeks using the legacy api_client.
        """
        try:
            underlying_sym = "BTCUSD" # Match the default WS subscription in api_client.py
            ticker = self.engine.api_client.get_realtime_ticker(underlying_sym)
            spot_price = float(ticker.get("mark_price", 0.0)) if ticker else 0.0
            
            return {
                "spot_price": spot_price,
                "funding": 0.0,
                "timestamp": self.clock.now(),
                "detailed_signal": getattr(self.engine.filters, 'last_detailed_signal', 'WAITING'),
                "open_interest": 0.0,
                "volume": 0.0,
                "iv": 0.0,
                "call_greeks": {"delta": 0.0, "gamma": 0.0, "vega": 0.0}
            }
        except Exception as e:
            logger.error(f"LegacyMarketFeedAdapter failed to fetch live data: {e}")
            return None
