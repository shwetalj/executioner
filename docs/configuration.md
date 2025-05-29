# Configuration Guide

This guide provides comprehensive documentation for configuring Executioner jobs and settings.

## Table of Contents

1. [Configuration File Structure](#configuration-file-structure)
2. [Global Settings](#global-settings)
3. [Job Configuration](#job-configuration)
4. [Environment Variables](#environment-variables)
5. [Retry Configuration](#retry-configuration)
6. [Validation Checks](#validation-checks)
7. [Email Notifications](#email-notifications)
8. [Security Settings](#security-settings)
9. [Advanced Features](#advanced-features)
10. [Configuration Examples](#configuration-examples)

## Configuration File Structure

Executioner uses JSON configuration files with the following top-level structure:

```json
{
  "application_name": "my_pipeline",
  "default_timeout": 3600,
  "parallel": true,
  "max_workers": 4,
  "env_variables": {},
  "email_address": "alerts@example.com",
  "jobs": []
}
```

## Global Settings

### Application Identification
- **application_name** (string): Unique identifier for your pipeline
  - Used in logging, database records, and notifications
  - Default: Configuration filename without extension

### Execution Control
- **parallel** (boolean): Enable parallel job execution
  - Default: `false` (sequential execution)
- **max_workers** (integer): Maximum number of concurrent jobs
  - Default: `1`
  - Only applies when `parallel: true`

### Timeout Settings
- **default_timeout** (integer): Default job timeout in seconds
  - Default: `3600` (1 hour)
  - Can be overridden per job

### Retry Defaults
- **default_max_retries** (integer): Default maximum retry attempts
  - Default: `0`
- **default_retry_delay** (integer): Default delay between retries (seconds)
  - Default: `60`
- **default_retry_backoff** (float): Default backoff multiplier
  - Default: `1.0` (no backoff)
- **default_retry_jitter** (float): Default jitter factor (0.0-1.0)
  - Default: `0.0` (no jitter)
- **default_max_retry_time** (integer): Default maximum total retry time
  - Default: `0` (no limit)
- **default_retry_on_exit_codes** (array): Default exit codes to retry on
  - Default: `[1]`

### Logging Configuration
- **log_dir** (string): Directory for log files
  - Default: `"./logs"`

### Security Settings
- **allow_shell** (boolean): Allow shell command execution
  - Default: `true`
- **security_policy** (string): Security validation level
  - Options: `"warn"`, `"strict"`
  - Default: `"warn"`

## Job Configuration

### Required Fields
Every job must have:
- **id** (string): Unique job identifier
- **command** (string): Command to execute

### Optional Fields

#### Basic Settings
- **description** (string): Human-readable job description
- **timeout** (integer): Job-specific timeout in seconds
- **dependencies** (array): List of job IDs this job depends on

#### Environment Variables
- **env_variables** (object): Job-specific environment variables
  ```json
  "env_variables": {
    "API_KEY": "secret-key",
    "DEBUG": "true",
    "DATA_PATH": "${BASE_PATH}/data"
  }
  ```

#### Retry Configuration
- **max_retries** (integer): Maximum retry attempts for this job
- **retry_delay** (integer): Delay between retries (seconds)
- **retry_backoff** (float): Backoff multiplier for retry delays
- **retry_jitter** (float): Random jitter factor (0.0-1.0)
- **max_retry_time** (integer): Maximum total time for retries
- **retry_on_status** (array): Status values to retry on
  - Options: `"ERROR"`, `"FAILED"`, `"TIMEOUT"`
- **retry_on_exit_codes** (array): Exit codes to retry on

#### Validation Checks
- **pre_checks** (array): Validations to run before job execution
- **post_checks** (array): Validations to run after job completion

### Example Job Configuration
```json
{
  "id": "data_processing",
  "description": "Process daily data files",
  "command": "python process_data.py --date ${PROCESS_DATE}",
  "dependencies": ["download_data", "validate_input"],
  "timeout": 1800,
  "env_variables": {
    "PROCESS_DATE": "${DATE}",
    "OUTPUT_DIR": "${BASE_PATH}/processed"
  },
  "max_retries": 3,
  "retry_delay": 30,
  "retry_backoff": 2.0,
  "retry_jitter": 0.1,
  "retry_on_exit_codes": [1, 2],
  "pre_checks": [
    {
      "name": "check_file_exists",
      "params": {"path": "${BASE_PATH}/input/data.csv"}
    }
  ],
  "post_checks": [
    {
      "name": "check_no_ora_errors",
      "params": {"log_file": "./logs/data_processing.log"}
    }
  ]
}
```

## Environment Variables

### Inheritance Control
- **inherit_shell_env** (boolean|string|array): Control environment inheritance
  - `true`: Inherit all shell variables (backward compatible)
  - `false`: Complete isolation (only explicit variables)
  - `"default"`: Inherit common system variables only
  - `["PATH", "HOME", ...]`: Custom whitelist of variables to inherit

### Variable Interpolation
Environment variables support `${VARIABLE_NAME}` interpolation:

```json
{
  "env_variables": {
    "BASE_PATH": "/opt/myapp",
    "CONFIG_PATH": "${BASE_PATH}/config",
    "LOG_PATH": "${BASE_PATH}/logs/${APPLICATION_NAME}",
    "FULL_PATH": "${CONFIG_PATH}/settings.json"
  }
}
```

### Variable Precedence
Environment variables are merged in this order (highest to lowest precedence):
1. CLI variables (`--env` flag)
2. Job-level variables
3. Application-level variables
4. Inherited shell variables (if enabled)

## Retry Configuration

### Retry Strategy Types

#### Simple Retry
```json
{
  "max_retries": 3,
  "retry_delay": 60
}
```

#### Exponential Backoff
```json
{
  "max_retries": 5,
  "retry_delay": 30,
  "retry_backoff": 2.0,
  "max_retry_time": 1800
}
```

#### Retry with Jitter
```json
{
  "max_retries": 3,
  "retry_delay": 60,
  "retry_jitter": 0.2
}
```

### Conditional Retries
```json
{
  "max_retries": 3,
  "retry_on_status": ["ERROR", "TIMEOUT"],
  "retry_on_exit_codes": [1, 2, 3]
}
```

## Validation Checks

### Built-in Checks

#### File Existence Check
```json
{
  "name": "check_file_exists",
  "params": {
    "path": "/path/to/required/file.txt"
  }
}
```

#### Oracle Error Check
```json
{
  "name": "check_no_ora_errors",
  "params": {
    "log_file": "./logs/job.log"
  }
}
```

### Custom Checks
You can create custom validation checks by extending the check registry system.

## Email Notifications

### Basic Email Configuration
```json
{
  "email_address": "alerts@example.com",
  "email_on_success": true,
  "email_on_failure": true,
  "smtp_server": "mail.example.com",
  "smtp_port": 587,
  "smtp_user": "user@example.com",
  "smtp_password": "password"
}
```

### Multiple Recipients
```json
{
  "email_address": [
    "team@example.com",
    "manager@example.com",
    "oncall@example.com"
  ]
}
```

### SMTP Configuration Options
- **smtp_server** (string): SMTP server hostname
- **smtp_port** (integer): SMTP server port
  - `25`: Plain SMTP
  - `587`: STARTTLS
  - `465`: SSL/TLS
- **smtp_user** (string): SMTP authentication username
- **smtp_password** (string): SMTP authentication password

## Security Settings

### Command Validation
```json
{
  "security_policy": "strict",
  "allow_shell": false
}
```

### Safe Command Patterns
When `security_policy: "strict"`, certain commands are blocked:
- Commands with `rm -rf`
- Commands with `sudo`
- Commands with dangerous file operations
- Commands with network operations to sensitive endpoints

### Environment Variable Security
- Sensitive variables are not logged
- Variables containing "password", "secret", "key", or "token" are masked in logs

## Advanced Features

### Dependency Plugins
```json
{
  "dependency_plugins": [
    "custom_dependency_module"
  ]
}
```

### Database Configuration
```json
{
  "database": {
    "type": "sqlite",
    "path": "./data/executioner.db"
  }
}
```

## Configuration Examples

### Simple Sequential Pipeline
```json
{
  "application_name": "data_pipeline",
  "default_timeout": 1800,
  "email_address": "team@example.com",
  "email_on_failure": true,
  "jobs": [
    {
      "id": "extract",
      "description": "Extract data from source",
      "command": "python extract.py"
    },
    {
      "id": "transform",
      "description": "Transform extracted data",
      "command": "python transform.py",
      "dependencies": ["extract"]
    },
    {
      "id": "load",
      "description": "Load data to destination",
      "command": "python load.py",
      "dependencies": ["transform"]
    }
  ]
}
```

### Parallel Processing Pipeline
```json
{
  "application_name": "parallel_pipeline",
  "parallel": true,
  "max_workers": 4,
  "env_variables": {
    "BASE_PATH": "/data/pipeline",
    "API_URL": "https://api.example.com"
  },
  "jobs": [
    {
      "id": "setup",
      "command": "python setup.py",
      "description": "Initialize pipeline"
    },
    {
      "id": "process_a",
      "command": "python process.py --dataset=A",
      "dependencies": ["setup"],
      "timeout": 3600
    },
    {
      "id": "process_b",
      "command": "python process.py --dataset=B",
      "dependencies": ["setup"],
      "timeout": 3600
    },
    {
      "id": "process_c",
      "command": "python process.py --dataset=C",
      "dependencies": ["setup"],
      "timeout": 3600
    },
    {
      "id": "finalize",
      "command": "python finalize.py",
      "dependencies": ["process_a", "process_b", "process_c"],
      "description": "Combine all results"
    }
  ]
}
```

### Enterprise Pipeline with Full Features
```json
{
  "application_name": "enterprise_pipeline",
  "default_timeout": 7200,
  "parallel": true,
  "max_workers": 6,
  "inherit_shell_env": ["PATH", "HOME", "USER"],
  "security_policy": "strict",
  "env_variables": {
    "PIPELINE_ENV": "production",
    "BASE_PATH": "/opt/enterprise_pipeline",
    "LOG_LEVEL": "INFO",
    "DB_CONNECTION": "${BASE_PATH}/config/db.json"
  },
  "email_address": ["ops@company.com", "data-team@company.com"],
  "email_on_success": true,
  "email_on_failure": true,
  "smtp_server": "mail.company.com",
  "smtp_port": 587,
  "smtp_user": "pipeline@company.com",
  "smtp_password": "${SMTP_PASSWORD}",
  "default_max_retries": 2,
  "default_retry_delay": 120,
  "default_retry_backoff": 1.5,
  "default_retry_jitter": 0.1,
  "jobs": [
    {
      "id": "health_check",
      "description": "Verify system health",
      "command": "python health_check.py",
      "timeout": 300,
      "pre_checks": [
        {
          "name": "check_file_exists",
          "params": {"path": "${DB_CONNECTION}"}
        }
      ]
    },
    {
      "id": "data_ingestion",
      "description": "Ingest data from multiple sources",
      "command": "python ingest.py --config ${DB_CONNECTION}",
      "dependencies": ["health_check"],
      "timeout": 3600,
      "max_retries": 3,
      "retry_delay": 300,
      "retry_backoff": 2.0,
      "env_variables": {
        "INGEST_MODE": "full",
        "PARALLEL_STREAMS": "4"
      }
    },
    {
      "id": "data_validation",
      "description": "Validate ingested data quality",
      "command": "python validate.py",
      "dependencies": ["data_ingestion"],
      "timeout": 1800,
      "post_checks": [
        {
          "name": "check_no_ora_errors",
          "params": {"log_file": "./logs/validation.log"}
        }
      ]
    },
    {
      "id": "reporting",
      "description": "Generate daily reports",
      "command": "python generate_reports.py",
      "dependencies": ["data_validation"],
      "timeout": 900
    }
  ]
}
```

## Best Practices

1. **Use descriptive job IDs and descriptions** for easier debugging
2. **Set appropriate timeouts** to prevent hung jobs
3. **Configure retries** for jobs that may have transient failures
4. **Use environment variables** for configuration that changes between environments
5. **Add validation checks** for critical prerequisites and success conditions
6. **Test configurations** with `--dry-run` before production deployment
7. **Monitor execution history** to identify patterns and optimize performance
8. **Use parallel execution** for independent jobs to reduce total runtime
9. **Set up email notifications** for critical production pipelines
10. **Keep sensitive information** in environment variables, not in configuration files

## Troubleshooting

### Common Configuration Errors
- **Circular Dependencies**: Use `--dry-run` to detect dependency cycles
- **Missing Dependencies**: Ensure all referenced job IDs exist
- **Invalid JSON**: Use a JSON validator to check syntax
- **Environment Variable Issues**: Check interpolation syntax and variable availability
- **Timeout Problems**: Monitor job execution times and adjust timeouts accordingly

### Validation Commands
```bash
# Validate configuration syntax
python executioner.py -c config.json --dry-run

# Check dependency resolution
python executioner.py -c config.json --dry-run --verbose

# Test environment variable interpolation
python executioner.py -c config.json --visible --dry-run
```