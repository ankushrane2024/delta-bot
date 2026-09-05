## Core Logic Protection Rule

**CRITICAL MANDATE FOR ALL AGENTS:** The core trading logic, execution pipeline, stop loss, and take profit systems of this bot are considered **LOCKED AND FINALIZED**. 

1. **DO NOT MODIFY** `bot_engine.py`, `smart_hedging.py`, or `execution.py` unless explicitly, specifically instructed by the user to fix a critical live bug.
2. **DO NOT ADD NEW MODULES OR FEATURES.** The bot is feature-complete.
3. If you are asked to debug or investigate, strictly limit your changes to UI (`dashboard.html`), API fetching (`filters.py`/`api_client.py`), or configuration adjustments.
4. If a bug requires modifying the core engine, you MUST present a detailed plan to the user explaining EXACTLY what will change and wait for explicit approval before writing any code.

# Task: Dual-Gateway Delta Demo & Live Account Management

- [x] Fix Delta Demo API credential validation failure (`testnet-api.delta.exchange`) <!-- id: 0 -->
- [x] Implement Multi-Gateway Auto-Detection across Live & Demo endpoints <!-- id: 1 -->
- [x] Build Dual-Slot Persistent Credentials Architecture (`live` and `demo` slots) <!-- id: 2 -->
- [x] Add guard on slot switching to unconfigured accounts (`➕ Configure Demo Key`) <!-- id: 3 -->
- [x] Decouple Demo Trading mode from real-money Live Armed toggle <!-- id: 4 -->
- [x] Verify on Local Cockpit & Deploy to Render Cloud (`https://delta-btc-options-bot.onrender.com/`) <!-- id: 5 -->
- [x] User enters Delta Demo Key and Secret to connect Demo account <!-- id: 6 -->
- [x] Demo API execution hard-isolated from Live account (network interceptor in api_client.py + execution gateway guard) <!-- id: 7 -->
- [x] Dynamic UI: all "Live" labels/cards switch to "Demo" when Demo API active (tab nav, hero bar, cockpit panel, dual-engine card, API badge) <!-- id: 8 -->
- [x] Fix DEMO lot size reading (use live_lots instead of total_lots) to prevent insufficient_margin error <!-- id: 9 -->
