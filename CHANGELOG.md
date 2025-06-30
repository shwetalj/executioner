# Changelog

All notable changes to the Executioner project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Week 1 Improvements (Zero Dependencies)

#### Added
- **Enhanced Exception Hierarchy** (`jobs/exceptions.py`)
  - Base `ExecutionerError` class with error codes, context, and timestamps
  - Specialized exceptions: `ConfigurationError`, `JobExecutionError`, `DependencyError`, etc.
  - `ErrorCodes` class with centralized error code constants
  - `to_dict()` method for exception serialization
  
- **Structured JSON Logging** (`executioner_logging/structured.py`)
  - `StructuredFormatter` for JSON log output
  - `ContextLogger` for maintaining context across log calls
  - Support for job_id, run_id, workflow_id context
  - Exception details in structured format
  - Optional hostname and process info
  
- **Enhanced Configuration Validator** (`config/validator.py`)
  - New validation functions added:
    - `validate_job_config()` - Individual job validation
    - `find_circular_dependencies()` - Detect dependency cycles
    - `validate_job_dependencies()` - Validate dependency graph
  - Detailed error messages
  - Type and business logic validation
  - Circular dependency detection
  - Duplicate dependency detection
  
- **Documentation**
  - `TESTING.md` - Comprehensive testing guide
  - `CHANGELOG.md` - This file

#### Changed
- Exception handling now provides more context for debugging
- All exceptions include timestamps and error codes
- Configuration validation provides clearer error messages

#### Technical Details
- All improvements use only Python standard library
- Maintains backward compatibility
- Python 3.6+ compatible
- Zero new dependencies

### Previous Versions

#### [1.0.0] - Initial Release
- Basic job execution engine
- Dependency management
- SQLite state persistence
- Email notifications
- Retry logic
- Pre/post execution checks

## Upgrade Guide

### From 1.0.0 to Week 1 Improvements

1. **Exception Handling**
   - Existing exception catches will continue to work
   - New exceptions provide additional context via `error_code` and `context` attributes
   - Use `exception.to_dict()` for structured error logging

2. **Logging**
   - To enable structured logging:
   ```python
   from executioner_logging import setup_structured_logging
   setup_structured_logging(level='INFO')
   ```
   - Existing logging calls will automatically output JSON

3. **Configuration Validation**
   - New validation functions can be used alongside the existing validator:
   ```python
   from config.validator import validate_job_config, validate_job_dependencies
   
   # Validate individual jobs
   errors = validate_job_config(job)
   
   # Check for dependency issues
   is_valid, dep_errors = validate_job_dependencies(config, logger)
   ```

## Roadmap

### Week 2 (Planned)
- Add type hints with typing_extensions
- Convert to dataclasses for cleaner code
- Improve state management

### Week 3 (Planned)
- Database abstraction layer
- Oracle support preparation
- SQL query optimization

### Week 4 (Planned)
- Metrics collection system
- Simple HTTP API
- Health check endpoints