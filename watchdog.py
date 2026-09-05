#!/usr/bin/env python3
"""
watchdog.py — Delta BTC Options Bot Crash Watchdog & Health Checker
===================================================================
Designed for Oracle Cloud VM systemd supervision.

Modes:
  1. --on-stop : Triggered by systemd ExecStopPost.
                 Inspects $SERVICE_RESULT, $EXIT_CODE, $EXIT_STATUS.
                 Differentiates clean manual stops from abnormal crashes.
                 Sends instant Telegram alert ONLY on actual failures.

  2. --check   : Performs an active health ping against the local /ping
                 endpoint. Can be run via cron or manually to test health.
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load .env
_env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=_env_path)

from notifier import notifier
from logger import app_logger

def handle_on_stop():
    """
    Evaluates systemd environment variables populated during ExecStopPost.
    Systemd passes:
      - SERVICE_RESULT: 'success', 'exit-code', 'signal', 'core-dump', 'watchdog', 'timeout'
      - EXIT_CODE:      'exited', 'killed', 'dumped'
      - EXIT_STATUS:    Integer exit code or signal number
    """
    service_result = os.environ.get('SERVICE_RESULT', 'unknown')
    exit_code = os.environ.get('EXIT_CODE', 'unknown')
    exit_status = os.environ.get('EXIT_STATUS', 'unknown')

    app_logger.info(f"Watchdog ExecStopPost invoked: result={service_result}, code={exit_code}, status={exit_status}")

    # Check if this was a clean, normal stop or restart
    is_clean = (service_result == 'success') or (exit_code == 'exited' and str(exit_status) in ('0', 'success'))

    if is_clean:
        app_logger.info("Watchdog: Clean service shutdown detected. No alert sent.")
        # Do not spam Telegram on planned maintenance or manual systemctl restart
        return 0

    # Abnormal termination / crash detected
    alert_msg = (
        f"🚨 <b>CRITICAL: Delta Bot Service Died on Oracle VM!</b>\n\n"
        f"<b>Failure Reason:</b> <code>{service_result}</code>\n"
        f"<b>Exit Code:</b> <code>{exit_code}</code>\n"
        f"<b>Exit Status/Signal:</b> <code>{exit_status}</code>\n\n"
        f"<i>systemd will automatically attempt restart in 5 seconds...</i>"
    )

    app_logger.critical(f"Watchdog alerting Telegram: Service crashed ({service_result})")
    try:
        notifier.send_message(alert_msg)
    except Exception as e:
        app_logger.error(f"Watchdog failed to send Telegram alert: {e}")

    return 1

def handle_check():
    """
    Active health check against localhost /ping endpoint.
    """
    import requests
    port = os.environ.get('PORT', '5000')
    url = os.environ.get('APP_URL', f'http://127.0.0.1:{port}').rstrip('/')
    target = f"{url}/ping"

    try:
        res = requests.get(target, timeout=8)
        if res.status_code == 200:
            print(f"[OK] Health check passed: {target} returned HTTP 200")
            return 0
        else:
            err_msg = f"HTTP {res.status_code}: {res.text[:100]}"
            print(f"[FAIL] Health check failed: {err_msg}")
            notifier.send_message(f"⚠️ <b>Watchdog Ping Warning:</b>\nEndpoint {target} returned {err_msg}")
            return 1
    except Exception as e:
        print(f"[FAIL] Health check connection error: {e}")
        notifier.send_message(f"🚨 <b>Watchdog Ping Failed:</b>\nCannot reach bot at {target}: {e}")
        return 1

def main():
    parser = argparse.ArgumentParser(description="Delta Bot Watchdog Utility")
    parser.add_argument('--on-stop', action='store_true', help="Called by systemd ExecStopPost on service stop")
    parser.add_argument('--check', action='store_true', help="Perform active HTTP health ping check")
    args = parser.parse_args()

    if args.on_stop:
        sys.exit(handle_on_stop())
    elif args.check:
        sys.exit(handle_check())
    else:
        parser.print_help()
        sys.exit(0)

if __name__ == '__main__':
    main()
