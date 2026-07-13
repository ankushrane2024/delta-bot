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
        
        # CRITICAL: Inject live BTC price for risk engine strike distance calculations
        ctx.futures_price = snapshot.metadata.get("futures_price", 0.0)
        
        # Unpack Live Metadata if available
        if "total_entry_premium" in snapshot.metadata:
            ctx.position_size = snapshot.metadata["total_entry_premium"]
            ctx.wallet_balance = snapshot.metadata.get("current_equity", 0.0)
            ctx.total_lots = snapshot.metadata.get("total_lots", 1)
            
            call_meta = snapshot.metadata.get("call_leg", {})
            put_meta = snapshot.metadata.get("put_leg", {})
            
            ctx.short_call_strike = call_meta.get("strike", 0.0)
            ctx.call_mark_price = call_meta.get("current_price", 0.0)
            ctx.call_delta = call_meta.get("delta", 0.0)
            ctx.call_gamma = call_meta.get("gamma", 0.0)
            ctx.call_vega = call_meta.get("vega", 0.0)
            ctx.call_iv = call_meta.get("iv", 0.0)
            
            ctx.short_put_strike = put_meta.get("strike", 0.0)
            ctx.put_mark_price = put_meta.get("current_price", 0.0)
            ctx.put_delta = put_meta.get("delta", 0.0)
            ctx.put_gamma = put_meta.get("gamma", 0.0)
            ctx.put_vega = put_meta.get("vega", 0.0)
            ctx.put_iv = put_meta.get("iv", 0.0)
            
            ctx.metadata['call_entry_premium_usd'] = call_meta.get("entry_premium_usd", 0.0)
            ctx.metadata['put_entry_premium_usd'] = put_meta.get("entry_premium_usd", 0.0)
            
            # CRITICAL: Populate per-leg PnL for Decision Engine Profit Override
            call_pnl = snapshot.metadata.get("call_pnl_usd", 0.0)
            put_pnl = snapshot.metadata.get("put_pnl_usd", 0.0)
            ctx.call_leg_pnl = call_pnl
            ctx.put_leg_pnl = put_pnl
            ctx.metadata['call_pnl_usd'] = call_pnl
            ctx.metadata['put_pnl_usd'] = put_pnl
            ctx.metadata['total_entry_premium'] = snapshot.metadata["total_entry_premium"]
            ctx.metadata['futures_price'] = ctx.futures_price
            ctx.metadata['hedge_pnl_usd'] = snapshot.metadata.get("hedge_pnl_usd", 0.0)
            
        return ctx
