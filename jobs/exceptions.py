"""
Custom exception hierarchy for the Executioner framework.

This module defines specific exception types for better error handling
and more precise error reporting throughout the system.
"""


class ExecutionerError(Exception):
    """Base exception for all executioner errors."""
    pass


class JobExecutionError(ExecutionerError):
    """Raised when job execution fails."""
    
    def __init__(self, job_id: str, message: str, exit_code: int = None):
        self.job_id = job_id
        self.exit_code = exit_code
        super().__init__(f"Job '{job_id}' failed: {message}")


class DependencyError(ExecutionerError):
    """Raised for dependency resolution issues."""
    
    def __init__(self, message: str, circular_deps: list = None, missing_deps: dict = None):
        self.circular_deps = circular_deps or []
        self.missing_deps = missing_deps or {}
        super().__init__(message)


class ConfigurationError(ExecutionerError):
    """Raised for configuration problems."""
    
    def __init__(self, message: str, config_file: str = None):
        self.config_file = config_file
        super().__init__(message)


class TimeoutError(JobExecutionError):
    """Raised when a job times out."""
    
    def __init__(self, job_id: str, timeout: int, message: str = None):
        self.timeout = timeout
        message = message or f"Job timed out after {timeout} seconds"
        super().__init__(job_id, message, exit_code=-1)


class RetryExhaustedError(JobExecutionError):
    """Raised when a job fails after all retries are exhausted."""
    
    def __init__(self, job_id: str, attempts: int, message: str = None):
        self.attempts = attempts
        message = message or f"Job failed after {attempts} attempts"
        super().__init__(job_id, message)


class PreCheckFailedError(JobExecutionError):
    """Raised when pre-execution checks fail."""
    
    def __init__(self, job_id: str, check_name: str, message: str = None):
        self.check_name = check_name
        message = message or f"Pre-check '{check_name}' failed"
        super().__init__(job_id, message)


class PostCheckFailedError(JobExecutionError):
    """Raised when post-execution checks fail."""
    
    def __init__(self, job_id: str, check_name: str, message: str = None):
        self.check_name = check_name
        message = message or f"Post-check '{check_name}' failed"
        super().__init__(job_id, message)


class DatabaseError(ExecutionerError):
    """Raised for database-related errors."""
    
    def __init__(self, message: str, operation: str = None):
        self.operation = operation
        super().__init__(message)


class NotificationError(ExecutionerError):
    """Raised when notification sending fails."""
    
    def __init__(self, message: str, notification_type: str = "email"):
        self.notification_type = notification_type
        super().__init__(message)