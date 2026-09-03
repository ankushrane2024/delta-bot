import urllib.request
import urllib.parse
import json

mermaid_code = """
flowchart TD
    %% Global Styling
    classDef external fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc
    classDef gate fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#f8fafc
    classDef engine fill:#0f172a,stroke:#3b82f6,stroke-width:2px,color:#f8fafc
    classDef ares fill:#4c1d95,stroke:#8b5cf6,stroke-width:2px,color:#f8fafc
    classDef db fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#f8fafc
    classDef execute fill:#b45309,stroke:#f59e0b,stroke-width:2px,color:#f8fafc

    %% 1. Market Data Ingestion
    subgraph MarketData ["1. Real-Time Market Data Ingestion"]
        WS["Deribit / Delta Exchange\nWebSockets (Real-Time)"]:::external
        Spot["BTC Spot Price"]:::external
        IV["DVOL (Implied Volatility)"]:::external
        Candles["15m Candles\n(Volume & Price)"]:::external
    end

    %% 2. Pre-Trade Filters & Master Gate
    subgraph PreTrade ["2. Trade Readiness & Master Gate (Every 9:00 / 9:30 AM)"]
        FilterEngine["Indicator Engine\nComputes ADX (Trend Strength) & RSI"]:::engine
        TrendState{"Market Regime State\nBULLISH / BEARISH / SIDEWAYS"}:::engine
        
        MasterGate{"MASTER GATE\n(Trade Readiness)"}:::gate
        GateRule1["Rule: DVOL Percentile (10% - 90%)"]:::gate
        GateRule2["Rule: Daily Loss Limit (< 2%)"]:::gate
        GateRule3["Rule: ADX/RSI Confluence"]:::gate
    end

    %% 3. Core Strategy Engine
    subgraph CoreStrategy ["3. Core Options Strategy Entry"]
        StrikeSelect["Dynamic Strike Selection\n(DVOL Mapping + Min 5 OTM)"]:::engine
        PremValid["Premium Validation\n(Min $100 per leg)"]:::engine
        PositionSizing["Dynamic Position Sizing\n(Base + DVOL Modifiers)"]:::engine
        LockAssign["Assign Hedge Lock\nOwner = 'ARES'"]:::engine
    end

    %% 4. Execution Bridge
    subgraph Bridge ["4. Exchange Execution & Bridge"]
        DeltaExec["Delta API Execution Module\n(Sells Short Strangle/Straddle)"]:::execute
        OptionBridge["OptionBridge Adapter\n(Live Portfolio Sync)"]:::execute
    end

    %% 5. ARES Pipeline (1Hz Tick Loop)
    subgraph ARESPipeline ["5. ARES High-Frequency Protection Pipeline (1 Tick/Sec)"]
        direction TB
        ARES_Start(("ARES Tick")):::ares
        
        A_Trend["Trend Engine\n(Price Action, Volume, Volatility)"]:::ares
        A_Regime["Regime Engine\n(Contextualizes Trend)"]:::ares
        A_Risk["Position Risk Engine\n(Calculates 4 Stress Clusters)"]:::ares
        
        subgraph Clusters ["The 4 Risk Clusters"]
            C_Dir["Directional Risk"]:::ares
            C_Vol["Volatility Risk"]:::ares
            C_Fin["Financial Risk (PnL)"]:::ares
            C_Ctx["Context Risk (Time/Gamma)"]:::ares
        end
        
        A_Fuse{"Fused Stress Score\n(0-100%)"}:::ares
        
        subgraph HardGates ["Decision Engine: 3 Hard Gates"]
            G1["Gate 1: Profit Override\n(Total PnL must be < 0)"]:::ares
            G2["Gate 2: Min Loss Threshold\n(Loss > 20% of Premium)"]:::ares
            G3["Gate 3: Confirmed Trend\n(Market must be Accelerating)"]:::ares
        end
        
        A_Size["Hedge Sizing Engine\n(Calculates exact BTC Delta)"]:::ares
        A_SM["Execution State Machine\n(Fires Market/Limit Orders)"]:::ares
    end

    %% 6. Exit & Square-Off
    subgraph Exits ["6. Exit & Square-Off Logic"]
        Exit_1700["Hard Exit (17:00 IST)\nCloses all options and hedges"]:::execute
        Exit_Reversal["Trend Reversal Rule\n(Options recover to -5% -> DEHEDGE)"]:::execute
        Exit_DPL["Dynamic Profit Lock (DPL)\n(Trailing Stop on Hedge Profit)"]:::execute
        Exit_SL["100% Single-Leg Stop Loss"]:::execute
    end

    %% Wiring it together
    WS --> Spot & IV & Candles
    Spot & Candles --> FilterEngine
    IV --> MasterGate
    FilterEngine --> TrendState
    TrendState --> MasterGate
    
    MasterGate -->|All Rules Pass| StrikeSelect
    MasterGate -.->|Fails| Blocked["TRADE BLOCKED"]:::gate
    
    StrikeSelect --> PremValid
    PremValid --> PositionSizing
    PositionSizing --> LockAssign
    LockAssign --> DeltaExec
    
    DeltaExec <--> OptionBridge
    OptionBridge --> ARES_Start
    
    ARES_Start --> A_Trend --> A_Regime --> A_Risk
    A_Risk --> Clusters --> A_Fuse
    A_Fuse --> HardGates
    
    HardGates -->|DANGER DETECTED| A_Size
    HardGates -.->|SAFE / REVERSAL| Exit_Reversal
    
    A_Size --> A_SM
    A_SM -->|Buy/Sell BTC Futures| OptionBridge
    
    %% Square off connections
    OptionBridge --> Exits
    Exit_DPL --> OptionBridge
    Exit_Reversal --> OptionBridge
"""

req = urllib.request.Request(
    'https://kroki.io/mermaid/pdf', 
    data=mermaid_code.encode('utf-8'), 
    headers={'Content-Type': 'text/plain'}
)

output_path = r'C:\Users\AnkushR\.gemini\antigravity\brain\4dabd903-b329-4561-9953-254b9dfe4462\ARES_Architecture.pdf'

try:
    with urllib.request.urlopen(req) as response:
        pdf_data = response.read()
        with open(output_path, 'wb') as f:
            f.write(pdf_data)
        print("Success! PDF saved to:", output_path)
except Exception as e:
    print("Error:", e)
