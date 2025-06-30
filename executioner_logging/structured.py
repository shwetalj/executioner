"""Structured logging implementation using only Python stdlib.

This module provides JSON-formatted structured logging capabilities
without requiring any external dependencies.
"""

import json
import logging
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, Optional


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging output."""
    
    def __init__(self, 
                 include_timestamp: bool = True,
                 include_hostname: bool = False,
                 include_process_info: bool = False):
        """Initialize the structured formatter.
        
        Args:
            include_timestamp: Whether to include timestamp in logs
            include_hostname: Whether to include hostname
            include_process_info: Whether to include process/thread info
        """
        super().__init__()
        self.include_timestamp = include_timestamp
        self.include_hostname = include_hostname
        self.include_process_info = include_process_info
        
        # Cache hostname if needed
        if include_hostname:
            import socket
            self.hostname = socket.gethostname()
    
    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON.
        
        Args:
            record: The log record to format
            
        Returns:
            JSON-formatted string
        """
        # Base log data
        log_data = {
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        
        # Add timestamp if requested
        if self.include_timestamp:
            log_data['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        
        # Add hostname if requested
        if self.include_hostname:
            log_data['hostname'] = self.hostname
        
        # Add process info if requested
        if self.include_process_info:
            import os
            import threading
            log_data['process'] = {
                'pid': os.getpid(),
                'thread_id': threading.current_thread().ident,
                'thread_name': threading.current_thread().name
            }
        
        # Add any custom attributes from the record
        # Common executioner-specific attributes
        for attr in ['job_id', 'run_id', 'workflow_id', 'dependency', 'error_code']:
            if hasattr(record, attr):
                value = getattr(record, attr)
                if value is not None:
                    log_data[attr] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add source location
        log_data['source'] = {
            'file': record.pathname,
            'line': record.lineno,
            'function': record.funcName
        }
        
        # Serialize to JSON
        try:
            return json.dumps(log_data, default=str)
        except (TypeError, ValueError):
            # Fallback for non-serializable objects
            log_data['message'] = str(log_data.get('message', ''))
            return json.dumps(log_data, default=str)


class ContextLogger:
    """Logger wrapper that maintains context across log calls."""
    
    def __init__(self, logger: logging.Logger, context: Optional[Dict[str, Any]] = None):
        """Initialize context logger.
        
        Args:
            logger: The underlying logger
            context: Initial context dictionary
        """
        self.logger = logger
        self.context = context or {}
    
    def with_context(self, **kwargs) -> 'ContextLogger':
        """Create a new logger with additional context.
        
        Returns:
            New ContextLogger with merged context
        """
        new_context = self.context.copy()
        new_context.update(kwargs)
        return ContextLogger(self.logger, new_context)
    
    def _log(self, level: int, msg: str, *args, **kwargs):
        """Internal log method that adds context."""
        # Merge context into extra
        extra = kwargs.get('extra', {})
        extra.update(self.context)
        kwargs['extra'] = extra
        
        # Log with context
        self.logger.log(level, msg, *args, **kwargs)
    
    def debug(self, msg: str, *args, **kwargs):
        """Log debug message with context."""
        self._log(logging.DEBUG, msg, *args, **kwargs)
    
    def info(self, msg: str, *args, **kwargs):
        """Log info message with context."""
        self._log(logging.INFO, msg, *args, **kwargs)
    
    def warning(self, msg: str, *args, **kwargs):
        """Log warning message with context."""
        self._log(logging.WARNING, msg, *args, **kwargs)
    
    def error(self, msg: str, *args, **kwargs):
        """Log error message with context."""
        self._log(logging.ERROR, msg, *args, **kwargs)
    
    def critical(self, msg: str, *args, **kwargs):
        """Log critical message with context."""
        self._log(logging.CRITICAL, msg, *args, **kwargs)
    
    def exception(self, msg: str, *args, **kwargs):
        """Log exception with context."""
        kwargs['exc_info'] = True
        self._log(logging.ERROR, msg, *args, **kwargs)


def setup_structured_logging(
    level: str = 'INFO',
    log_file: Optional[str] = None,
    include_timestamp: bool = True,
    include_hostname: bool = False,
    include_process_info: bool = False
) -> logging.Logger:
    """Set up structured JSON logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
        include_timestamp: Whether to include timestamps
        include_hostname: Whether to include hostname
        include_process_info: Whether to include process/thread info
        
    Returns:
        Configured root logger
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter
    formatter = StructuredFormatter(
        include_timestamp=include_timestamp,
        include_hostname=include_hostname,
        include_process_info=include_process_info
    )
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Add file handler if requested
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    return root_logger


def get_logger(name: str, context: Optional[Dict[str, Any]] = None) -> ContextLogger:
    """Get a context-aware logger for a module.
    
    Args:
        name: Logger name (usually __name__)
        context: Initial context dictionary
        
    Returns:
        ContextLogger instance
    """
    logger = logging.getLogger(name)
    return ContextLogger(logger, context)


# Convenience function to log structured data
def log_event(logger: logging.Logger, level: str, event: str, **data):
    """Log a structured event with arbitrary data.
    
    Args:
        logger: The logger to use
        level: Log level
        event: Event name/type
        **data: Additional structured data
    """
    extra = {'event': event}
    extra.update(data)
    logger.log(getattr(logging, level.upper()), event, extra=extra)