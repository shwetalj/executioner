import os
from config.loader import Config

def ensure_log_dir():
    """Ensure log directory is created securely."""
    os.makedirs(Config.LOG_DIR, exist_ok=True, mode=0o755) 