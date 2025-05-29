# Executioner Test Suite

This directory contains a comprehensive test suite for the Executioner job execution engine (/home/sjoshi/claudelab/maestro/maestro.py). The tests cover all the major features and command-line options of the tool.

## Test Structure

- **`test_scripts/`**: Contains Python scripts that simulate different job behaviors:
  - `success_script.py`: Always succeeds
  - `failure_script.py`: Always fails
  - `timeout_script.py`: Runs for a long time to test timeout functionality
  - `retry_script.py`: Fails on first attempts but succeeds after retries

- **`config/`**: Contains different JSON configuration files for testing various features:
  - `basic_test.json`: Simple sequential job execution
  - `parallel_test.json`: Tests parallel execution with dependencies
  - `failures_test.json`: Tests job failures
  - `circular_deps_test.json`: Tests circular dependency detection
  - `missing_deps_test.json`: Tests missing dependency handling
  - `retry_test.json`: Tests retry functionality
  - `shell_commands_test.json`: Tests shell command execution
  - `security_test.json`: Tests security warning system

## Running the Tests

### Run All Tests

To run all tests in sequence:

```bash
./run_all_tests.sh
```

This script will execute all test configurations with various command-line options to test all features of the Executioner.

### Run Individual Tests

You can also run individual tests by directly invoking /home/sjoshi/claudelab/maestro/maestro.py with the appropriate configuration file:

```bash
# Basic test
python3 /home/sjoshi/claudelab/maestro/maestro.py -c config/basic_test.json

# Parallel execution test
python3 /home/sjoshi/claudelab/maestro/maestro.py -c config/parallel_test.json --parallel

# Test with failures
python3 /home/sjoshi/claudelab/maestro/maestro.py -c config/failures_test.json --continue-on-error

# Dry run test
python3 /home/sjoshi/claudelab/maestro/maestro.py -c config/basic_test.json --dry-run
```

## Test Coverage

The test suite covers the following key features:

1. **Basic Job Execution**: Sequential execution of jobs with dependencies
2. **Parallel Execution**: Parallel execution with proper dependency resolution
3. **Error Handling**: Handling of job failures and timeout conditions
4. **Command-line Options**: 
   - `--continue-on-error`: Continue executing jobs even if some fail
   - `--dry-run`: Simulate execution without running actual commands
   - `--skip`: Skip specific jobs
   - `--env`: Pass environment variables from the command line
   - `--parallel`: Enable parallel execution
   - `--workers`: Configure number of parallel workers
   - `--sequential`: Force sequential execution
   - `--resume-from`: Resume from a previous run
   - `--resume-failed-only`: Re-run only failed jobs from a previous run
5. **Dependency Resolution**: Proper handling of job dependencies, detection of missing and circular dependencies
6. **Shell Command Support**: Testing of shell features like pipes, redirects, etc.
7. **Security Features**: Testing of command validation and security policy enforcement
8. **Retry Mechanism**: Testing of job retry functionality

## Logs

Execution logs will be stored in the `logs/` directory, organized by application name and run ID.

## Clean Up

After running the tests, you may want to clean up temporary files:

```bash
rm -f /tmp/test_output.txt
rm -rf /tmp/test_dir
rm -f /tmp/retry_script_executions.txt
```