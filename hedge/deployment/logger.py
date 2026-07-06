import logging
import logging.handlers
import json
import os
import re

class SecretRedactingFormatter(logging.Formatter):
    """
    JSON log formatter that enforces secret redaction.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.secrets = []

    def set_secrets(self, secrets: list):
        self.secrets = [s for s in secrets if s]

    def format(self, record):
        # Build JSON dictionary from log record
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        # Stringify to run redaction
        log_json = json.dumps(log_record)
        
        # Redact known secrets (e.g., API keys, signatures)
        for secret in self.secrets:
            log_json = log_json.replace(secret, "***REDACTED***")
            
        # Redact Authorization headers or generic patterns if they slip through
        log_json = re.sub(r'("Authorization":\s*")Bearer\s+[^"]+(")', r'\1***REDACTED***\2', log_json, flags=re.IGNORECASE)
        log_json = re.sub(r'("api-key":\s*")[^"]+(")', r'\1***REDACTED***\2', log_json, flags=re.IGNORECASE)
        log_json = re.sub(r'("signature":\s*")[^"]+(")', r'\1***REDACTED***\2', log_json, flags=re.IGNORECASE)
        
        return log_json

def setup_logger(name: str, log_dir: str, secrets: list = None) -> logging.Logger:
    """
    Creates or retrieves a JSON structured logger for a specific subsystem.
    Subsystems map to specific log files (e.g. system.log, execution.log).
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Avoid attaching multiple handlers if called multiple times
    if logger.handlers:
        return logger
        
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{name}.log")
    
    # Rotating file handler (Midnight rotation, keep 7 days)
    handler = logging.handlers.TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=7
    )
    
    formatter = SecretRedactingFormatter()
    if secrets:
        formatter.set_secrets(secrets)
        
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False # Prevent double logging to root
    
    return logger

def initialize_all_loggers(log_dir: str, config):
    """
    Initializes the canonical 7 rotators as per Module 39 constraints.
    """
    secrets = [config.delta_api_key, config.delta_api_secret] if config else []
    
    # We create the requested loggers
    setup_logger("startup", log_dir, secrets)
    setup_logger("system", log_dir, secrets)
    setup_logger("provider", log_dir, secrets)
    setup_logger("execution", log_dir, secrets)
    setup_logger("dashboard", log_dir, secrets)
    setup_logger("audit", log_dir, secrets)
    setup_logger("recovery", log_dir, secrets)

    # Redirect root logging to system logger (so imported libraries don't spew unstructured logs)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    system_handler = logging.handlers.TimedRotatingFileHandler(
        os.path.join(log_dir, "system.log"), when="midnight", interval=1, backupCount=7
    )
    
    formatter = SecretRedactingFormatter()
    formatter.set_secrets(secrets)
    system_handler.setFormatter(formatter)
    root_logger.addHandler(system_handler)
