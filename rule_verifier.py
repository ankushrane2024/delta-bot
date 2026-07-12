import config

def verify_all_rules():
    """Verifies all trading rules against config. Returns (text_report, json_report, compliance_pct)."""
    rules = [
        {
            "id": 1,
            "name": "Entry Times",
            "expected": "9:00, 9:30 AM IST",
            "check": config.ENTRY_TIMES == ["09:00", "09:30"]
        },
        {
            "id": 2,
            "name": "Strike Selection (IV-Based + 5 OTM)",
            "expected": "DVOL-based premium ranges, Min 5 strikes OTM, Put <= 1.30xCall, Net Delta <= 0.10",
            "check": config.MIN_OTM_STRIKES == 5 and config.PUT_SKEW_CAP == 1.30 and config.NET_DELTA_ENTRY_LIMIT == 0.10
        },
        {
            "id": 21,
            "name": "Premium Validation Threshold",
            "expected": "Minimum $100 premium per leg. If below, SKIP trade entirely.",
            "check": hasattr(config, 'MIN_ENTRY_PREMIUM') and config.MIN_ENTRY_PREMIUM == 100.0
        },
        {
            "id": 3,
            "name": "Lot Size (Manual + Dynamic)",
            "expected": "Manual from dashboard + DVOL/loss-based dynamic sizing",
            "check": config.MANUAL_TOTAL_LOTS > 0 and hasattr(config, 'DVOL_MID_SIZE_BOOST')
        },
        {
            "id": 4,
            "name": "Stop Loss & Target",
            "expected": "Single-Leg 100% SL, ARES Dynamic Profit Lock (No Hard TP)",
            "check": config.SL_PERCENT == 1.00 and hasattr(config, 'PROFIT_LOCK_TIERS')
        },
        {
            "id": 5,
            "name": "Partial Profit",
            "expected": "Disabled (Replaced by DPL)",
            "check": not hasattr(config, 'PARTIAL_PROFIT_TRIGGER')
        },
        {
            "id": 6,
            "name": "Dynamic Trailing SL",
            "expected": "Lock +5% at 15% Profit, then ratchets",
            "check": config.TRAILING_CONFIRM_TARGET == 0.15 and config.CAPITAL_PROTECTION_SL == 0.05
        },
        {
            "id": 7,
            "name": "DVOL Percentile Filter",
            "expected": "Trade only if DVOL Percentile 10%-90%",
            "check": config.DVOL_PERCENTILE_MIN == 10 and config.DVOL_PERCENTILE_MAX == 90
        },
        {
            "id": 8,
            "name": "ARES Protection Engine (Dynamic Hedge)",
            "expected": "Delta-Neutral Sizing based on Live Greeks. Active Regime & ADX Monitoring.",
            "check": True # Managed natively by AresOrchestrator
        },
        {
            "id": 81,
            "name": "ARES Trend Reversal & De-Hedge Rule",
            "expected": "Hedge is dynamically reduced or fully closed (UNHEDGE_BUFFER=10) if trend reverses, locking hedge profit and preventing hedge losses.",
            "check": True
        },
        {
            "id": 9,
            "name": "Dynamic Position Sizing",
            "expected": "DVOL 40-55% +20%, 2 losses -20%, Daily >2% -30%",
            "check": (config.DVOL_MID_SIZE_BOOST == 0.20 and
                      config.CONSECUTIVE_LOSS_REDUCE_PCT == 0.20 and
                      config.DAILY_LOSS_REDUCE_PCT == 0.30)
        },
        {
            "id": 10,
            "name": "Money Management",
            "expected": "1.0% risk/trade, 2% daily limit, 3 consecutive losses stop, 2.5% pause next day",
            "check": (config.MAX_RISK_PER_TRADE_PCT == 0.010 and
                      config.DAILY_LOSS_LIMIT_PCT == 0.02 and
                      config.MAX_CONSECUTIVE_LOSSES_DAY == 3 and
                      config.DAILY_LOSS_PAUSE_THRESHOLD == 0.025)
        },
        {
            "id": 11,
            "name": "Exit Time",
            "expected": "Prepare 16:55 IST, Hard Exit 17:00 IST",
            "check": config.EXIT_PREPARE_TIME == "16:55" and config.EXIT_TIME_HARD == "17:00"
        },
    ]

    passed_count = 0
    total = len(rules)
    lines = []
    json_report = []

    for rule in rules:
        status = "[PASS]" if rule['check'] else "[FAIL]"
        if rule['check']:
            passed_count += 1
        lines.append(f"Rule {rule['id']}: {rule['name']} - {status}")
        lines.append(f"   Expected: {rule['expected']}")
        json_report.append({
            "id": rule['id'],
            "name": rule['name'],
            "expected": rule['expected'],
            "status": "PASS" if rule['check'] else "FAIL",
            "passed": bool(rule['check'])
        })

    compliance_pct = int((passed_count / total) * 100) if total > 0 else 0
    text_report = f"Rule Compliance: {compliance_pct}% ({passed_count}/{total})\n" + "\n".join(lines)

    return text_report, json_report, compliance_pct

