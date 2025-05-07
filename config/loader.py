from pathlib import Path

class Config:
    """Configuration constants for the executioner."""
    BASE_DIR = Path(__file__).resolve().parent
    # Use current working directory for logs
    CWD = Path.cwd()
    LOG_DIR = (CWD / 'logs').resolve()
    DB_FILE = BASE_DIR / 'jobs_history.db'
    DEFAULT_TIMEOUT = 600
    MAX_LOG_SIZE = 10 * 1024 * 1024
    BACKUP_LOG_COUNT = 5

    # ANSI Colors
    COLOR_BLUE = "\033[94m"
    COLOR_DARK_GREEN = "\033[32m"
    COLOR_RED = "\033[91m"
    COLOR_CYAN = "\033[36m"
    COLOR_YELLOW = "\033[93m"
    COLOR_MAGENTA = "\033[95m"
    COLOR_RESET = "\033[0m" 
