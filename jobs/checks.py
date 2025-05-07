import os

def check_file_exists(path):
    """Return True if the file at 'path' exists."""
    return os.path.isfile(path)

def check_no_ora_errors(log_file):
    """Return True if the log file does NOT contain any ORA- errors."""
    try:
        with open(log_file) as f:
            for line in f:
                if "ORA-" in line:
                    return False
        return True
    except Exception:
        return False

def check_no_ora_or_sp2_errors(log_file):
    """Return True if the log file does NOT contain any ORA- or SP2- errors."""
    try:
        with open(log_file) as f:
            for line in f:
                if "ORA-" in line or "SP2-" in line:
                    return False
        return True
    except Exception:
        return False 

CHECK_REGISTRY = {
    "check_file_exists": check_file_exists,
    "check_no_ora_errors": check_no_ora_errors,
    "check_no_ora_or_sp2_errors": check_no_ora_or_sp2_errors,
}
