# Testing Guide for Executioner

This document describes how to test the Executioner system and its components.

## Overview

The Executioner uses pytest for testing. All tests should be run from the project root directory.

## Running Tests

### All Tests
```bash
pytest
```

### Specific Test File
```bash
pytest tests/test_exceptions.py
```

### With Coverage
```bash
pytest --cov=jobs --cov=config --cov=db --cov-report=html
```

## Test Structure

```
tests/
├── test_exceptions.py       # Exception hierarchy tests
├── test_structured_logging.py   # JSON logging tests
├── test_validator.py        # Configuration validator tests
├── test_integration.py      # Integration tests
└── fixtures/               # Test configuration files
    ├── valid_config.json
    ├── invalid_config.json
    └── circular_deps.json
```

## Writing Tests

### Testing Exceptions

```python
import pytest
from jobs.exceptions import JobExecutionError, ErrorCodes

def test_job_execution_error():
    """Test JobExecutionError with context."""
    error = JobExecutionError(
        job_id='test_job',
        message='Command failed',
        exit_code=1,
        error_code=ErrorCodes.JOB_COMMAND_FAILED
    )
    
    assert error.job_id == 'test_job'
    assert error.exit_code == 1
    assert error.error_code == ErrorCodes.JOB_COMMAND_FAILED
    
    # Test serialization
    error_dict = error.to_dict()
    assert error_dict['error_type'] == 'JobExecutionError'
    assert error_dict['context']['job_id'] == 'test_job'
```

### Testing Structured Logging

```python
import json
import logging
from executioner_logging import setup_structured_logging, get_logger

def test_structured_logging(capfd):
    """Test JSON log output."""
    setup_structured_logging(level='INFO')
    logger = get_logger(__name__)
    
    logger.info("Test message", extra={'job_id': 'test'})
    
    # Capture output
    out, _ = capfd.readouterr()
    log_entry = json.loads(out.strip())
    
    assert log_entry['level'] == 'INFO'
    assert log_entry['message'] == 'Test message'
    assert log_entry['job_id'] == 'test'
```

### Testing Configuration Validation

```python
from config.validator import validate_job_config, find_circular_dependencies

def test_circular_dependencies():
    """Test circular dependency detection."""
    jobs = {
        "a": {"id": "a", "command": "echo a", "dependencies": ["b"]},
        "b": {"id": "b", "command": "echo b", "dependencies": ["a"]}
    }
    
    cycles = find_circular_dependencies(jobs)
    
    assert len(cycles) > 0
    assert any('a' in cycle and 'b' in cycle for cycle in cycles)
```

## Integration Testing

### Testing Job Execution

```python
def test_job_execution_with_logging(tmp_path):
    """Test job execution with structured logging."""
    config = {
        "working_dir": str(tmp_path),
        "jobs": [
            {
                "id": "test_job",
                "command": "echo 'Hello, World!'",
                "timeout": 10
            }
        ]
    }
    
    # Run executioner
    result = run_executioner(config)
    
    assert result.exit_code == 0
    assert result.jobs_succeeded == 1
```

## Test Fixtures

### Valid Configuration
```json
{
    "working_dir": "/tmp/executioner_test",
    "jobs": [
        {
            "id": "setup",
            "command": "mkdir -p output",
            "timeout": 5
        },
        {
            "id": "process",
            "command": "echo 'Processing' > output/result.txt",
            "dependencies": ["setup"],
            "timeout": 10
        }
    ]
}
```

### Invalid Configuration
```json
{
    "jobs": [
        {
            "command": "echo 'Missing ID'"
        }
    ]
}
```

## Mocking and Patching

### Mocking External Commands

```python
from unittest.mock import patch, MagicMock

@patch('subprocess.run')
def test_job_runner(mock_run):
    """Test job runner with mocked subprocess."""
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout='Success',
        stderr=''
    )
    
    # Test job execution
    result = run_job({"id": "test", "command": "echo test"})
    
    assert result.exit_code == 0
    mock_run.assert_called_once()
```

## Performance Testing

### Testing Parallel Execution

```python
import time

def test_parallel_performance():
    """Test parallel job execution performance."""
    config = {
        "working_dir": "/tmp",
        "max_parallel": 4,
        "jobs": [
            {
                "id": f"job_{i}",
                "command": "sleep 1",
                "timeout": 5
            }
            for i in range(10)
        ]
    }
    
    start_time = time.time()
    result = run_executioner(config)
    duration = time.time() - start_time
    
    # Should complete in ~3 seconds (10 jobs / 4 parallel)
    assert duration < 4
    assert result.jobs_succeeded == 10
```

## Debugging Tests

### Enable Debug Logging
```bash
pytest -v -s --log-cli-level=DEBUG
```

### Run Specific Test
```bash
pytest -k "test_circular_dependencies" -v
```

### Debug with PDB
```python
def test_complex_scenario():
    import pdb; pdb.set_trace()  # Debugger breakpoint
    # Test code here
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.6, 3.7, 3.8, 3.9]
    
    steps:
    - uses: actions/checkout@v2
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-minimal.txt
    - name: Run tests
      run: |
        pytest --cov=jobs --cov=config --cov=db
```

## Best Practices

1. **Test Isolation**: Each test should be independent
2. **Clear Names**: Test names should describe what they test
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Mock External Dependencies**: Don't rely on external systems
5. **Test Edge Cases**: Empty lists, None values, timeouts
6. **Use Fixtures**: Share common test data efficiently
7. **Test Error Cases**: Ensure proper error handling

## Common Issues

### Import Errors
If you encounter import errors, ensure you're running tests from the project root:
```bash
cd /path/to/executioner
pytest
```

### Permission Errors
Some tests may require write permissions. Use pytest's tmp_path fixture:
```python
def test_with_files(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
```

### Timeout Issues
For tests that might hang, use pytest-timeout:
```bash
pip install pytest-timeout
pytest --timeout=300  # 5 minute timeout
```