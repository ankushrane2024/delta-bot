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
    """Calculates the D2 (tomorrow) expiry date string for Delta Exchange."""
    now = get_ist_now()
    tomorrow = now + datetime.timedelta(days=1)
    return tomorrow.strftime('%d%m%y') # e.g. 120526

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

