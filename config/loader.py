from pathlib import Path

class Config:
    """Configuration constants for the executioner."""
    BASE_DIR = Path(__file__).resolve().parent
    # Use current working directory for logs
    CWD = Path.cwd()
    LOG_DIR = None  # Set after config is loaded
    DB_FILE = BASE_DIR / 'jobs_history.db'
    DEFAULT_TIMEOUT = 600
    MAX_LOG_SIZE = 10 * 1024 * 1024
    BACKUP_LOG_COUNT = 5

    # ANSI Colors - Optimized for both light and dark backgrounds
    COLOR_BLUE = "\033[38;5;33m"      # Dodger Blue - works well on both
    COLOR_DARK_GREEN = "\033[38;5;28m" # Forest Green - good contrast
    COLOR_RED = "\033[38;5;196m"       # Bright Red - universally visible
    COLOR_CYAN = "\033[38;5;33m"       # Same as Blue (Dodger Blue)
    COLOR_YELLOW = "\033[38;5;208m"    # Dark Orange - readable on both backgrounds
    COLOR_MAGENTA = "\033[38;5;201m"   # Hot Magenta - vibrant on both
    COLOR_RESET = "\033[0m" 

    @classmethod
    def set_log_dir(cls, log_dir):
        cls.LOG_DIR = Path(log_dir).resolve() 
        