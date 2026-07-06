from hedge.models.portfolio import PortfolioSnapshot
from hedge.context.position_context import PositionContext

class PositionContextAdapter:
    """
    Adapter that maps the immutable PortfolioSnapshot into the primitive PositionContext
    expected by the PositionRiskEngine and DecisionEngine, strictly enforcing the PortfolioSynchronizer 
    as the single source of truth without modifying the existing engines.
    """
    
    @staticmethod
    def from_snapshot(snapshot: PortfolioSnapshot) -> PositionContext:
        ctx = PositionContext()
        ctx.net_delta = snapshot.combined_delta
        ctx.futures_delta = snapshot.net_futures_delta
        ctx.options_delta = snapshot.net_options_delta
        ctx.total_pnl = snapshot.total_pnl
        ctx.margin_usage = snapshot.margin_used
        ctx.hedge_ratio = snapshot.hedge_ratio
        ctx.is_hedged = snapshot.futures_position_qty != 0
        ctx.timestamp = snapshot.timestamp
        return ctx
