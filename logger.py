import logging
import os
from datetime import datetime
import pytz

def get_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return datetime.now(ist)

class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.ist_time = get_ist_time().strftime('%Y-%m-%d %H:%M:%S IST')
        return super().format(record)

def setup_logger(name, log_file, level=logging.INFO):
    """Function to setup as many loggers as you want"""
    
    formatter = CustomFormatter('%(ist_time)s - %(name)s - %(levelname)s - %(message)s')

    handler = logging.FileHandler(log_file)        
    handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(console_handler)

    return logger

# Main application logger
app_logger = setup_logger('BotCore', 'trading_bot.log')
trade_logger = setup_logger('TradeLog', 'trades.log')
error_logger = setup_logger('ErrorLog', 'errors.log', level=logging.ERROR)
