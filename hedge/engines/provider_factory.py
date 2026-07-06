from hedge.models.core_interfaces import Clock, SystemClock
from hedge.models.events import EventBus
from hedge.engines.execution_provider import AbstractExecutionProvider, PaperExecutionProvider
from hedge.engines.delta.provider import DeltaExecutionProvider
import config

class ProviderFactory:
    @staticmethod
    def create_provider(clock: Clock, event_bus: EventBus) -> AbstractExecutionProvider:
        mode = getattr(config, "BOT_MODE", "PAPER").upper()
        if mode == "LIVE":
            api_key = getattr(config, "DELTA_API_KEY", "")
            api_secret = getattr(config, "DELTA_API_SECRET", "")
            rest_url = getattr(config, "DELTA_INDIA_BASE_URL", "https://api.india.delta.exchange")
            ws_url = getattr(config, "DELTA_INDIA_WS_URL", "wss://socket.india.delta.exchange")
            return DeltaExecutionProvider(api_key, api_secret, rest_url, ws_url, event_bus, clock=clock)
        else:
            return PaperExecutionProvider(clock=clock)
