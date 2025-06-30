"""
Custom exception hierarchy for the Executioner framework.

This module defines specific exception types for better error handling
and more precise error reporting throughout the system.

Enhanced with:
- Structured error codes for categorization
- Context dictionaries for debugging information
- Timestamps for error tracking
- Serialization support for logging
"""

from datetime import datetime
from typing import Optional, Dict, Any


class ExecutionerError(Exception):
    """Base exception for all executioner errors.
    
    Provides structured error information including:
    - Error message
    - Error code for categorization
    - Context dictionary for additional debugging info
    - Timestamp of when the error occurred
    """
    
    def __init__(self, 
                 message: str, 
                 error_code: str = 'UNKNOWN', 
                 context: Optional[Dict[str, Any]] = None):
        """Initialize the base exception.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code (e.g., 'E001', 'CFG002')
            context: Optional dictionary with additional context
        """
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}
        self.timestamp = datetime.utcnow()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            'error_type': self.__class__.__name__,
            'message': str(self),
            'error_code': self.error_code,
            'context': self.context,
            'timestamp': self.timestamp.isoformat()
        }


class JobExecutionError(ExecutionerError):
    """Raised when job execution fails."""
    
    def __init__(self, job_id: str, message: str, exit_code: int = None, 
                 error_code: str = 'JOB001', context: Optional[Dict[str, Any]] = None):
        self.job_id = job_id
        self.exit_code = exit_code
        
        # Build context
        if context is None:
            context = {}
        context['job_id'] = job_id
        if exit_code is not None:
            context['exit_code'] = exit_code
            
        super().__init__(f"Job '{job_id}' failed: {message}", error_code, context)


class DependencyError(ExecutionerError):
    """Raised for dependency resolution issues."""
    
    def __init__(self, message: str, circular_deps: list = None, missing_deps: dict = None,
                 error_code: str = 'DEP001', context: Optional[Dict[str, Any]] = None):
        self.circular_deps = circular_deps or []
        self.missing_deps = missing_deps or {}
        
        # Build context
        if context is None:
            context = {}
        if circular_deps:
            context['circular_dependencies'] = circular_deps
        if missing_deps:
            context['missing_dependencies'] = missing_deps
            
        super().__init__(message, error_code, context)


class ConfigurationError(ExecutionerError):
    """Raised for configuration problems."""
    
    def __init__(self, message: str, config_file: str = None, 
                 error_code: str = 'CFG001', context: Optional[Dict[str, Any]] = None):
        self.config_file = config_file
        
        # Build context
        if context is None:
            context = {}
        if config_file:
            context['config_file'] = config_file
            
        super().__init__(message, error_code, context)


class TimeoutError(JobExecutionError):
    """Raised when a job times out."""
    
    def __init__(self, job_id: str, timeout: int, message: str = None, 
                 context: Optional[Dict[str, Any]] = None):
        self.timeout = timeout
        message = message or f"Job timed out after {timeout} seconds"
        
        # Build context
        if context is None:
            context = {}
        context['timeout_seconds'] = timeout
        
        super().__init__(job_id, message, exit_code=-1, error_code='JOB002', context=context)


class RetryExhaustedError(JobExecutionError):
    """Raised when a job fails after all retries are exhausted."""
    
    def __init__(self, job_id: str, attempts: int, message: str = None,
                 context: Optional[Dict[str, Any]] = None):
        self.attempts = attempts
        message = message or f"Job failed after {attempts} attempts"
        
        # Build context
        if context is None:
            context = {}
        context['attempts'] = attempts
        
        super().__init__(job_id, message, error_code='JOB003', context=context)


class PreCheckFailedError(JobExecutionError):
    """Raised when pre-execution checks fail."""
    
    def __init__(self, job_id: str, check_name: str, message: str = None,
                 context: Optional[Dict[str, Any]] = None):
        self.check_name = check_name
        message = message or f"Pre-check '{check_name}' failed"
        
        # Build context
        if context is None:
            context = {}
        context['check_name'] = check_name
        context['check_type'] = 'pre'
        
        super().__init__(job_id, message, error_code='JOB004', context=context)


class PostCheckFailedError(JobExecutionError):
    """Raised when post-execution checks fail."""
    
    def __init__(self, job_id: str, check_name: str, message: str = None,
                 context: Optional[Dict[str, Any]] = None):
        self.check_name = check_name
        message = message or f"Post-check '{check_name}' failed"
        
        # Build context
        if context is None:
            context = {}
        context['check_name'] = check_name
        context['check_type'] = 'post'
        
        super().__init__(job_id, message, error_code='JOB005', context=context)


class DatabaseError(ExecutionerError):
    """Raised for database-related errors."""
    
    def __init__(self, message: str, operation: str = None, query: str = None,
                 error_code: str = 'DB001', context: Optional[Dict[str, Any]] = None):
        self.operation = operation
        
        # Build context
        if context is None:
            context = {}
        if operation:
            context['operation'] = operation
        if query:
            context['failed_query'] = query
            
        super().__init__(message, error_code, context)


class NotificationError(ExecutionerError):
    """Raised when notification sending fails."""
    
    def __init__(self, message: str, notification_type: str = "email",
                 error_code: str = 'NOTIF001', context: Optional[Dict[str, Any]] = None):
        self.notification_type = notification_type
        
        # Build context
        if context is None:
            context = {}
        context['notification_type'] = notification_type
        
        super().__init__(message, error_code, context)


class StateError(ExecutionerError):
    """Raised when state management operations fail."""
    pass


class ValidationError(ExecutionerError):
    """Raised when input validation fails."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Any = None,
                 error_code: str = 'VAL001', context: Optional[Dict[str, Any]] = None):
        """Initialize validation error with field-specific info."""
        
        # Build context
        if context is None:
            context = {}
        if field:
            context['field'] = field
        if value is not None:
            context['invalid_value'] = str(value)
            
        super().__init__(message, error_code, context)


# Error code constants for consistency
class ErrorCodes:
    """Centralized error codes for the system."""
    
    # Configuration errors (CFG)
    CONFIG_NOT_FOUND = 'CFG001'
    CONFIG_INVALID_JSON = 'CFG002'
    CONFIG_MISSING_FIELD = 'CFG003'
    CONFIG_INVALID_TYPE = 'CFG004'
    CONFIG_VALIDATION_FAILED = 'CFG005'
    
    # Job execution errors (JOB)
    JOB_COMMAND_FAILED = 'JOB001'
    JOB_TIMEOUT = 'JOB002'
    JOB_RETRY_EXHAUSTED = 'JOB003'
    JOB_PRE_CHECK_FAILED = 'JOB004'
    JOB_POST_CHECK_FAILED = 'JOB005'
    JOB_NOT_FOUND = 'JOB006'
    JOB_ALREADY_RUNNING = 'JOB007'
    JOB_CANCELLED = 'JOB008'
    
    # Dependency errors (DEP)
    DEPENDENCY_NOT_FOUND = 'DEP001'
    DEPENDENCY_FAILED = 'DEP002'
    CIRCULAR_DEPENDENCY = 'DEP003'
    DEPENDENCY_TIMEOUT = 'DEP004'
    
    # State errors (STATE)
    STATE_CORRUPTED = 'STATE001'
    STATE_TRANSITION_INVALID = 'STATE002'
    STATE_LOCK_FAILED = 'STATE003'
    
    # Database errors (DB)
    DB_CONNECTION_FAILED = 'DB001'
    DB_QUERY_FAILED = 'DB002'
    DB_TRANSACTION_FAILED = 'DB003'
    DB_CONSTRAINT_VIOLATION = 'DB004'
    
    # Validation errors (VAL)
    VALIDATION_TYPE_ERROR = 'VAL001'
    VALIDATION_RANGE_ERROR = 'VAL002'
    VALIDATION_FORMAT_ERROR = 'VAL003'
    VALIDATION_REQUIRED_FIELD = 'VAL004'
    
    # Notification errors (NOTIF)
    NOTIFICATION_SEND_FAILED = 'NOTIF001'
    NOTIFICATION_CONFIG_ERROR = 'NOTIF002'