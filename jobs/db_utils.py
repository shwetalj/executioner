import sqlite3
from functools import wraps

def handle_db_errors(logger):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except sqlite3.Error as e:
                logger.error(f"Database error in {func.__name__}: {e}")
                raise
        return wrapper
    return decorator 