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
            "name": "Strike Selection (Min 5 OTM + $90 Premium)",
            "expected": "Min 5 strikes OTM, Premium >= $90, Max 20% Premium Skew, Net Delta <= 0.10",
            "check": config.MIN_OTM_STRIKES == 5 and config.NET_DELTA_ENTRY_LIMIT == 0.10
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
            "expected": "130% SL, 30% Full Target",
            "check": config.SL_PERCENT == 1.30 and config.EXIT_PROFIT_TARGET == 0.30
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
            "expected": "IV-based thresholds: <45% delta>0.15, 45-55% delta>0.12, >55% delta>0.08",
            "check": (hasattr(config, 'HEDGE_IV_THRESHOLDS') and
                      config.HEDGE_IV_THRESHOLDS['low']['delta_trigger'] == 0.15 and
                      config.HEDGE_IV_THRESHOLDS['mid']['delta_trigger'] == 0.12 and
                      config.HEDGE_IV_THRESHOLDS['high']['delta_trigger'] == 0.08)
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

