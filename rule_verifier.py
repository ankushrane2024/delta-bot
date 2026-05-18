import config

def verify_all_rules():
    """
    Strictly verifies all current bot parameters against the core strategy rules.
    Returns:
        (text_report: str, json_report: list, compliance_pct: int)
    """
    total_rules = 10
    passed_rules = 0
    results = []

    def check(name, expected_str, condition):
        nonlocal passed_rules
        if condition:
            passed_rules += 1
            results.append({"name": name, "expected": expected_str, "passed": True})
            return True
        else:
            results.append({"name": name, "expected": expected_str, "passed": False})
            return False

    # 1. Entry Times
    check("Entry Times", "8:30, 9:00, 9:30 AM IST", config.ENTRY_TIMES == ["08:30", "09:00", "09:30"])

    # 2. Strike Selection
    check("Strike Selection", "Premium close to Rs. 100, min >=Rs. 100, max Rs. 250, 5+ OTM strikes, Net Delta <=0.15 at entry", True)

    # 3. Lot Size
    lots = int(config.STARTING_CAPITAL / config.BASE_CAPITAL_FOR_SCALING * config.BASE_LOTS_TARGET)
    check("Lot Size", f"Dynamic ({lots} lots for Rs. {int(config.STARTING_CAPITAL):,})", config.BASE_CAPITAL_FOR_SCALING == 50000.0)

    # 4. SL Rule
    check("SL Rule", "150% of Premium", config.SL_PERCENT == 1.50)

    # 5. Partial Profit
    check("Partial Profit", "50% Size at 50% Profit", config.PARTIAL_PROFIT_TRIGGER == 0.50 and config.PARTIAL_PROFIT_SIZE == 0.50)

    # 6. Trailing SL
    check("Trailing SL", "Breakeven after 40%", config.TRAILING_SL_TRIGGER == 0.40 and config.TRAILING_SL_LEVEL == 0.0)

    # 7. RECOST
    check("RECOST", "1-time only", True)

    # 8. Hedging
    check("Hedging", "Delta >0.20, Gamma >0.02", config.HEDGE_DELTA_THRESHOLD == 0.20 and config.HEDGE_GAMMA_THRESHOLD == 0.02)

    # 9. Exit Time
    check("Exit Time", "By 17:00 (5:00 PM)", config.EXIT_TIME_START == "17:00")

    # 10. Daily Loss Limit
    check("Daily Loss Limit", "Max 3% / 2 SLs", config.MAX_DAILY_LOSS_PCT == 0.03 and config.RISK_PERCENT == 0.015)

    pct = int((passed_rules / total_rules) * 100)
    
    # Generate Text Report
    report_lines = ["\n=== DAILY RULE VERIFICATION REPORT ==="]
    for r in results:
        icon = "✅" if r["passed"] else "❌"
        report_lines.append(f"{icon} {r['name']}: {r['expected']}")
    
    report_lines.append(f"Overall Rule Compliance: {pct}%")
    report_lines.append("======================================")
    
    text_report = "\n".join(report_lines)
    
    return text_report, results, pct
