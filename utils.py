import datetime
import pytz

def get_ist_now():
    """Returns current datetime in IST."""
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.datetime.now(ist)

def format_ist_time(dt):
    """Formats a datetime object to a readable IST string."""
    return dt.strftime('%Y-%m-%d %H:%M:%S IST')

def is_within_time_range(current_time_str, start_time_str, end_time_str):
    """Checks if current_time (HH:MM) is between start and end."""
    return start_time_str <= current_time_str <= end_time_str

def get_next_expiry_date():
    """Calculates the appropriate expiry date string for Delta Exchange BTC options.

    BTC options on Delta Exchange expire at approximately 17:28 IST each day.
    - Before 17:28 IST  → use TODAY's expiry (same-day contracts, highest premium)
    - After  17:28 IST  → use TOMORROW's expiry (today's contracts gone from chain)

    Returns:
        str: Expiry date in '%d%m%y' format, e.g. '121026'
    """
    EXPIRY_HOUR   = 17   # 5 PM IST
    EXPIRY_MINUTE = 28   # :28

    now = get_ist_now()
    current_minutes = now.hour * 60 + now.minute

    # Use today's expiry if we are still before the 17:28 cutoff
    if current_minutes < EXPIRY_HOUR * 60 + EXPIRY_MINUTE:
        expiry_date = now
    else:
        expiry_date = now + datetime.timedelta(days=1)

    return expiry_date.strftime('%d%m%y')  # e.g. '121026'

def calculate_pnl(entry_price, current_price, size, side='SELL'):
    """Calculates USDT PnL for a position."""
    if side == 'SELL':
        return (entry_price - current_price) * size
    else:
        return (current_price - entry_price) * size

def should_check_hedge(last_hedge_check_time):
    """
    Hedging schedule: 
    - Every 60 min (morning: before 2:00 PM IST)
    - Every 30 min (afternoon: after 2:00 PM IST)
    """
    now = get_ist_now()
    if not last_hedge_check_time:
        return True
        
    diff_minutes = (now - last_hedge_check_time).total_seconds() / 60.0
    
    # Check if after 2 PM IST (14:00)
    is_afternoon = now.hour >= 14
    
    if is_afternoon and diff_minutes >= 30:
        return True
    elif not is_afternoon and diff_minutes >= 60:
        return True
        
    return False

def adjust_time_to_system_tz(time_str):
    """
    Converts an 'HH:MM' time string (assumed to be in IST timezone) 
    to the system local time 'HH:MM' string for the scheduler.
    """
    import datetime
    import pytz
    
    # 1. Parse HH:MM in IST today
    ist_tz = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.datetime.now(ist_tz)
    h, m = map(int, time_str.split(':'))
    
    # Construct datetime object in IST
    ist_dt = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
    
    # 2. Convert to system local timezone
    system_tz = datetime.datetime.now().astimezone().tzinfo
    
    # Convert IST time to system timezone
    system_dt = ist_dt.astimezone(system_tz)
    
    return system_dt.strftime('%H:%M')

