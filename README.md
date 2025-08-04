# Executioner - Job Execution Engine

A robust, dependency-aware job execution engine with parallel processing, retry capabilities, and comprehensive monitoring.

## Overview

Executioner is a sophisticated job orchestration system that reads JSON configuration files and executes jobs with proper dependency resolution. It supports both sequential and parallel execution modes, comprehensive retry strategies, pre/post-job validation checks, and detailed execution history tracking.

## Quick Start

```bash
# Basic execution
python executioner.py -c jobs_config.json

# Parallel execution with 4 workers
python executioner.py -c jobs_config.json --parallel --workers 4

# Dry run to validate configuration
python executioner.py -c jobs_config.json --dry-run

# Resume a failed run
python executioner.py -c jobs_config.json --resume-from 123
```

## Key Features

### 🚀 **Execution Modes**
- **Sequential Execution**: Jobs run one after another in dependency order
- **Parallel Execution**: Independent jobs run simultaneously with configurable worker pools
- **Dry Run Mode**: Validate configuration and show execution plan without running jobs

### 🔗 **Dependency Management**
- **Smart Dependency Resolution**: Automatic topological sorting of job dependencies
- **Circular Dependency Detection**: Prevents infinite loops and configuration errors
- **Dynamic Job Queuing**: Jobs are queued as their dependencies complete
- **Plugin Support**: Custom dependency types via plugin system

### 🔄 **Advanced Retry Capabilities**
- **Configurable Retry Logic**: Per-job retry counts, delays, and backoff strategies
- **Exponential Backoff**: Intelligent retry timing with jitter to prevent thundering herd
- **Conditional Retries**: Retry based on exit codes, status, or custom conditions
- **Retry History Tracking**: Complete audit trail of all retry attempts

### ✅ **Validation & Checks**
- **Pre-execution Checks**: Validate prerequisites before job execution
- **Post-execution Checks**: Verify job success conditions after completion
- **Built-in Check Library**: File existence, Oracle error detection, and more
- **Custom Check Support**: Extensible validation framework

### 📊 **Monitoring & Reporting**
- **Comprehensive Logging**: Detailed logs for main execution and individual jobs
- **Execution History**: Complete database tracking of all runs and job statuses
- **Rich Summary Reports**: Color-coded status, timing, and dependency information
- **Email Notifications**: Configurable alerts for success/failure with log attachments

### 🛡️ **Security & Safety**
- **Command Validation**: Security policies to prevent dangerous command execution
- **Environment Isolation**: Controlled environment variable inheritance
- **Safe Resume Operations**: Mark failed jobs as successful with audit trails
- **Configuration Validation**: Comprehensive schema validation with helpful error messages

### 🔧 **Operations & Maintenance**
- **Resume Functionality**: Restart from any previous run, with options to retry only failed jobs
- **Job Skipping**: Skip specific jobs during execution
- **Interactive Operations**: Mark jobs as successful, view detailed run information
- **Database Management**: SQLite-based persistence with migration support

### 🌐 **Environment Management**
- **Variable Interpolation**: Support for `${VAR_NAME}` substitution in configuration
- **Layered Environment**: Application, job-level, and CLI environment variables with proper precedence
- **Shell Environment Control**: Fine-grained control over shell environment inheritance
- **Secure Variable Handling**: Prevent logging of sensitive information

### 📈 **Performance & Scalability**
- **Thread Pool Management**: Efficient resource utilization with configurable worker pools
- **Memory Optimization**: Efficient handling of large job configurations
- **Timeout Management**: Per-job and global timeout controls
- **Resource Monitoring**: Track memory and CPU usage for optimization

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd executioner

# Install dependencies
pip install -r requirements.txt
```

## Configuration

Create a JSON configuration file with your jobs and settings:

```bash
# Generate a sample configuration
python executioner.py --sample-config > my_jobs.json
```

See [Configuration Guide](docs/configuration.md) for detailed configuration options.

## Usage Examples

```bash
# Execute jobs with custom environment variables
python executioner.py -c config.json --env "DEBUG=true,API_URL=https://api.example.com"

# Skip specific jobs
python executioner.py -c config.json --skip job1,job2,job3

# Continue execution even if jobs fail
python executioner.py -c config.json --continue-on-error

# View execution history
python executioner.py --list-runs

# Get detailed information about a specific run
python executioner.py --show-run 123

# Mark failed jobs as successful for resume operations
python executioner.py --mark-success -r 123 -j failed_job1,failed_job2
```

## Architecture

Executioner follows a modular architecture with single-responsibility components:

- **JobExecutioner**: Main coordinator and entry point
- **ExecutionOrchestrator**: Controls execution flow and job scheduling
- **QueueManager**: Manages job queuing and state tracking
- **StateManager**: Handles run lifecycle and timing
- **JobRunner**: Executes individual jobs with monitoring
- **DependencyManager**: Resolves and validates job dependencies
- **NotificationManager**: Handles email alerts and notifications
- **ExecutionHistoryManager**: Persists execution data to database

See [Architecture Documentation](docs/architecture.md) for detailed diagrams and component interactions.

## Documentation

- [Configuration Guide](docs/configuration.md) - Detailed configuration options and examples
- [Usage Guide](docs/usage.md) - Advanced usage patterns and best practices
- [Architecture](docs/architecture.md) - System design and component diagrams
- [API Reference](docs/api.md) - Internal API documentation

## Requirements

- Python 3.6+
- SQLite3 (included with Python)
- Standard library dependencies only

## License

[License information to be added]

## Contributing

[Contributing guidelines to be added]

## Support

For issues and feature requests, please use the project's issue tracker.