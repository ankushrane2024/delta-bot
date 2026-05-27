import config

def verify_all_rules():
    """Verifies all trading rules against config. Returns (text_report, json_report, compliance_pct)."""
    rules = [
        {
            "id": 1,
            "name": "Entry Times",
            "expected": "8:30, 9:00, 9:30 AM IST",
            "check": config.ENTRY_TIMES == ["08:30", "09:00", "09:30"]
        },
        {
            "id": 2,
            "name": "Strike Selection (IV-Based + 4 OTM)",
            "expected": "DVOL-based premium ranges, Min 4 strikes OTM, Put <= 1.35xCall, Net Delta <= 0.15",
            "check": config.MIN_OTM_STRIKES == 4 and config.PUT_SKEW_CAP == 1.35 and config.NET_DELTA_ENTRY_LIMIT == 0.15
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
            "expected": "150% SL, 30% Full Target",
            "check": config.SL_PERCENT == 1.50 and config.EXIT_PROFIT_TARGET == 0.30
        },
        {
            "id": 5,
            "name": "Partial Profit",
            "expected": "50% Size at 20% Profit",
            "check": config.PARTIAL_PROFIT_TRIGGER == 0.20 and config.PARTIAL_PROFIT_SIZE == 0.50
        },
        {
            "id": 6,
            "name": "Trailing Stop Loss",
            "expected": "Breakeven after 15% Profit",
            "check": config.TRAILING_SL_TRIGGER == 0.15 and config.TRAILING_SL_LEVEL == 0.0
        },
        {
            "id": 7,
            "name": "DVOL Percentile Filter",
            "expected": "Trade only if DVOL Percentile 10%-90%",
            "check": config.DVOL_PERCENTILE_MIN == 10 and config.DVOL_PERCENTILE_MAX == 90
        },
        {
            "id": 8,
            "name": "Smart Hedging",
            "expected": "IV-based thresholds: <45% delta>0.20, 45-55% delta>0.17, >55% delta>0.12",
            "check": (hasattr(config, 'HEDGE_IV_THRESHOLDS') and
                      config.HEDGE_IV_THRESHOLDS['low']['delta_trigger'] == 0.20 and
                      config.HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] == 0.17 and
                      config.HEDGE_IV_THRESHOLDS['high']['delta_trigger'] == 0.12)
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
            "expected": "1.5% risk/trade, 3% daily limit, 3 consecutive losses stop, 2.5% pause next day",
            "check": (config.MAX_RISK_PER_TRADE_PCT == 0.015 and
                      config.DAILY_LOSS_LIMIT_PCT == 0.03 and
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

