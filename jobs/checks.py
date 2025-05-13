import os
import glob
import logging

def check_file_exists(path):
    """Return True if the file at 'path' exists."""
    return os.path.isfile(path)

def check_no_ora_errors(log_file):
    """Return True if the log file(s) do NOT contain any ORA- errors. Supports wildcards. Adds debug output."""
    logger = logging.getLogger("check_no_ora_errors")
    matched_files = glob.glob(log_file)
    logger.debug(f"[DEBUG] check_no_ora_errors: log_file pattern: {log_file}")
    logger.debug(f"[DEBUG] check_no_ora_errors: matched_files: {matched_files}")
    if not matched_files:
        logger.error(f"[DEBUG] check_no_ora_errors: No files matched for pattern: {log_file}")
        return False
    for file_path in matched_files:
        try:
            logger.debug(f"[DEBUG] check_no_ora_errors: Checking file: {file_path}")
            with open(file_path) as f:
                for line in f:
                    if "ORA-" in line:
                        logger.error(f"[DEBUG] check_no_ora_errors: Found ORA- error in file: {file_path}")
                        return False
        except Exception as e:
            logger.error(f"[DEBUG] check_no_ora_errors: Exception opening file {file_path}: {e}")
            return False
    logger.debug(f"[DEBUG] check_no_ora_errors: No ORA- errors found in any matched files.")
    return True

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
