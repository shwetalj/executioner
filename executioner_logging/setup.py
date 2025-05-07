import os
from config.loader import Config

def ensure_log_dir():
    """Ensure log directory is created securely."""
    try:
        os.makedirs(Config.LOG_DIR, exist_ok=True, mode=0o755)
    except PermissionError:
        # Fallback to a directory in the same location as the script
        Config.LOG_DIR = os.path.join(Config.BASE_DIR, 'logs')
        os.makedirs(Config.LOG_DIR, exist_ok=True)
        print(f"Warning: Could not create logs directory in current working directory. Using {Config.LOG_DIR} instead.") 