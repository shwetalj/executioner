# Usage Guide

This guide covers advanced usage patterns, best practices, and detailed examples for Executioner.

## Table of Contents

1. [Command Line Interface](#command-line-interface)
2. [Execution Modes](#execution-modes)
3. [Resume and Recovery](#resume-and-recovery)
4. [Environment Management](#environment-management)
5. [Monitoring and Debugging](#monitoring-and-debugging)
6. [Advanced Workflows](#advanced-workflows)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)

## Command Line Interface

### Basic Usage
```bash
# Run with default configuration file (jobs_config.json)
python executioner.py

# Specify configuration file
python executioner.py -c my_pipeline.json

# Show sample configuration
python executioner.py --sample-config
```

### Execution Control Options

#### Dry Run Mode
```bash
# Validate configuration and show execution plan
python executioner.py -c config.json --dry-run

# Dry run with verbose output
python executioner.py -c config.json --dry-run --verbose
```

#### Parallel Execution
```bash
# Enable parallel execution (overrides config)
python executioner.py -c config.json --parallel

# Set number of workers
python executioner.py -c config.json --parallel --workers 8

# Force sequential execution
python executioner.py -c config.json --sequential
```

#### Job Skipping
```bash
# Skip specific jobs
python executioner.py -c config.json --skip job1,job2,job3

# Multiple skip arguments
python executioner.py -c config.json --skip job1 --skip job2,job3

# Continue execution even if jobs fail
python executioner.py -c config.json --continue-on-error
```

### Environment Variables
```bash
# Set single environment variable
python executioner.py -c config.json --env "DEBUG=true"

# Set multiple variables
python executioner.py -c config.json --env "DEBUG=true,API_URL=https://api.example.com"

# Multiple env arguments
python executioner.py -c config.json --env "DEBUG=true" --env "LOG_LEVEL=info"
```

### Logging and Debugging
```bash
# Enable debug logging
python executioner.py -c config.json --debug

# Enable verbose logging
python executioner.py -c config.json --verbose

# Show all environment variables
python executioner.py -c config.json --visible
```

## Execution Modes

### Sequential Execution
Default mode where jobs run one after another based on dependency order.

```bash
python executioner.py -c config.json
```

**Use Cases:**
- Resource-constrained environments
- Jobs that require exclusive access to resources
- Simple linear workflows
- Debugging complex dependency issues

### Parallel Execution
Jobs with satisfied dependencies run simultaneously.

```bash
python executioner.py -c config.json --parallel --workers 4
```

**Use Cases:**
- Independent data processing tasks
- Multi-dataset workflows
- CPU/IO intensive workloads
- Time-sensitive pipelines

### Dry Run Mode
Validates configuration and shows execution plan without running jobs.

```bash
python executioner.py -c config.json --dry-run
```

**Output Example:**
```
===============================
DRY RUN EXECUTION PLAN
===============================
Total Jobs: 5
Parallel Mode: Sequential

Execution Order:
1. setup_database (no dependencies)
2. load_data (depends on: setup_database)
3. process_data_a (depends on: load_data)
4. process_data_b (depends on: load_data)
5. generate_report (depends on: process_data_a, process_data_b)

Estimated Runtime: 45-60 minutes
```

## Resume and Recovery

### Basic Resume Operations

#### Resume from Previous Run
```bash
# Resume all incomplete jobs from run 123
python executioner.py -c config.json --resume-from 123

# Resume only failed jobs (skip successful ones)
python executioner.py -c config.json --resume-from 123 --resume-failed-only
```

#### View Execution History
```bash
# List recent runs
python executioner.py --list-runs

# List runs for specific application
python executioner.py --list-runs my_pipeline

# Show detailed run information
python executioner.py --show-run 123
```

### Manual Job Success Marking

Mark failed jobs as successful to continue execution:

```bash
# Mark specific jobs as successful
python executioner.py --mark-success -r 123 -j job1,job2,job3

# Interactive confirmation will be requested
```

**Example Workflow:**
```bash
# 1. Check failed run details
python executioner.py --show-run 123

# 2. Mark known-good jobs as successful
python executioner.py --mark-success -r 123 -j data_cleanup,validation

# 3. Resume execution
python executioner.py -c config.json --resume-from 123
```

### Resume Strategies

#### Full Resume
Restarts all incomplete jobs (failed, errored, or not yet started):
```bash
python executioner.py -c config.json --resume-from 123
```

#### Failed-Only Resume
Only retries jobs that explicitly failed:
```bash
python executioner.py -c config.json --resume-from 123 --resume-failed-only
```

#### Selective Resume with Skipping
Skip problematic jobs and resume others:
```bash
python executioner.py -c config.json --resume-from 123 --skip problematic_job1,problematic_job2
```

## Environment Management

### Environment Variable Hierarchy

Variables are applied in this precedence order:
1. **CLI Variables** (`--env` flag) - Highest precedence
2. **Job-Level Variables** (in job configuration)
3. **Application-Level Variables** (in global config)
4. **Shell Environment** (if inheritance enabled) - Lowest precedence

### Variable Interpolation Examples

```json
{
  "env_variables": {
    "BASE_PATH": "/opt/myapp",
    "DATA_DIR": "${BASE_PATH}/data",
    "LOG_FILE": "${DATA_DIR}/processing_${DATE}.log",
    "ARCHIVE_PATH": "${BASE_PATH}/archive/${YEAR}/${MONTH}"
  }
}
```

### Shell Environment Control

#### Full Inheritance (Default)
```json
{
  "inherit_shell_env": true
}
```

#### Complete Isolation
```json
{
  "inherit_shell_env": false
}
```

#### Selective Inheritance
```json
{
  "inherit_shell_env": ["PATH", "HOME", "USER", "LANG"]
}
```

#### Default System Variables Only
```json
{
  "inherit_shell_env": "default"
}
```

### Environment Debugging

```bash
# Show environment for all jobs
python executioner.py -c config.json --visible --dry-run

# Show environment for first job only
python executioner.py -c config.json --verbose --dry-run
```

## Monitoring and Debugging

### Execution History

#### List Recent Runs
```bash
# Show last 20 runs
python executioner.py --list-runs

# Show last 10 runs for specific app
python executioner.py --list-runs my_pipeline
```

**Output Example:**
```
Recent Execution History:
================================================================================
Run ID | Application      | Status    | Start Time          | Duration | Jobs
--------------------------------------------------------------------------------
   125 | data_pipeline    | SUCCESS   | 2024-01-15 09:30:15 | 01:23:45 |  5/5
   124 | data_pipeline    | FAILED    | 2024-01-15 08:15:22 | 00:45:30 |  3/5 (2 failed)
   123 | data_pipeline    | SUCCESS   | 2024-01-14 09:30:10 | 01:18:20 |  5/5
```

#### Detailed Run Information
```bash
python executioner.py --show-run 124
```

**Output Example:**
```
Run Details for ID 124:
================================================================================
Application: data_pipeline
Status: FAILED
Start Time: 2024-01-15 08:15:22
End Time: 2024-01-15 09:00:52
Duration: 00:45:30
Total Jobs: 5

Job Status Details:
--------------------------------------------------------------------------------

✓ Successful Jobs (3):
  setup_database               - Initialize database tables
  load_raw_data               - Load data from CSV files
  validate_data               - Run data quality checks

✗ Failed Jobs (2):
  process_analytics           - Generate analytics summaries [FAILED]
    Command: python analytics.py --input /data/raw --output /data/processed
    Time: 2024-01-15 08:45:22
  generate_reports            - Create daily reports [TIMEOUT]
    Command: python reports.py --date 2024-01-15
    Time: 2024-01-15 09:00:52

Resume Options:
--------------------------------------------------------------------------------
To resume all incomplete jobs:
  executioner.py -c config.json --resume-from 124

To retry only failed jobs:
  executioner.py -c config.json --resume-from 124 --resume-failed-only

To mark failed jobs as successful:
  executioner.py --mark-success -r 124 -j process_analytics,generate_reports

Log Files:
--------------------------------------------------------------------------------
Main log: ./logs/executioner.data_pipeline.run-124.log
Job log:  ./logs/executioner.data_pipeline.job-process_analytics.run-124.log
Job log:  ./logs/executioner.data_pipeline.job-generate_reports.run-124.log
```

### Log Files

#### Log File Structure
```
logs/
├── executioner.{app_name}.run-{run_id}.log     # Main execution log
├── executioner.{app_name}.job-{job_id}.run-{run_id}.log  # Individual job logs
└── executioner.{app_name}.summary-{run_id}.log # Summary and notifications
```

#### Log Levels
- **ERROR**: Critical failures and errors
- **WARNING**: Non-fatal issues and configuration problems
- **INFO**: Normal execution progress and status updates
- **DEBUG**: Detailed execution information and troubleshooting data

### Performance Monitoring

#### Execution Timing Analysis
```bash
# Run with timing information
python executioner.py -c config.json --verbose

# Monitor long-running jobs
tail -f logs/executioner.my_app.run-125.log | grep "RUNNING"
```

#### Resource Usage Tracking
Job logs include resource usage information:
- Execution time
- Memory usage (if available)
- CPU usage (if available)
- Exit codes and status

## Advanced Workflows

### Multi-Environment Deployments

#### Development Environment
```bash
python executioner.py -c config.json \
    --env "ENV=dev,API_URL=https://dev-api.example.com,DEBUG=true" \
    --verbose
```

#### Production Environment
```bash
python executioner.py -c config.json \
    --env "ENV=prod,API_URL=https://api.example.com,DEBUG=false" \
    --parallel --workers 8
```

### Conditional Job Execution

#### Skip Jobs Based on Conditions
```bash
# Skip non-essential jobs in emergency mode
python executioner.py -c config.json \
    --skip "analytics,reporting,archival" \
    --continue-on-error
```

#### Environment-Specific Skipping
```bash
# Skip integration tests in production
if [ "$ENV" = "production" ]; then
    SKIP_JOBS="integration_tests,load_tests"
else
    SKIP_JOBS=""
fi

python executioner.py -c config.json --skip "$SKIP_JOBS"
```

### Automated Recovery Workflows

#### Retry Failed Jobs Script
```bash
#!/bin/bash
# auto_retry.sh

CONFIG_FILE="pipeline.json"
MAX_RETRIES=3
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    echo "Attempt $((RETRY_COUNT + 1)) of $MAX_RETRIES"
    
    python executioner.py -c "$CONFIG_FILE" --parallel
    EXIT_CODE=$?
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Pipeline completed successfully"
        exit 0
    fi
    
    echo "Pipeline failed, waiting 300 seconds before retry..."
    sleep 300
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

echo "Pipeline failed after $MAX_RETRIES attempts"
exit 1
```

#### Smart Resume Script
```bash
#!/bin/bash
# smart_resume.sh

# Get the last failed run ID
LAST_FAILED_RUN=$(python executioner.py --list-runs | grep FAILED | head -1 | awk '{print $1}')

if [ -n "$LAST_FAILED_RUN" ]; then
    echo "Resuming failed run: $LAST_FAILED_RUN"
    python executioner.py -c config.json --resume-from "$LAST_FAILED_RUN" --resume-failed-only
else
    echo "No failed runs found, starting new execution"
    python executioner.py -c config.json
fi
```

### Integration with External Systems

#### CI/CD Pipeline Integration
```yaml
# .github/workflows/pipeline.yml
name: Data Pipeline
on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM

jobs:
  data-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run pipeline
        run: |
          python executioner.py -c production.json \
            --env "DATE=$(date +%Y-%m-%d)" \
            --parallel --workers 4
        env:
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
          API_KEY: ${{ secrets.API_KEY }}
```

#### Cron Job Integration
```bash
# Add to crontab with: crontab -e
# Run daily at 2 AM
0 2 * * * cd /opt/data-pipeline && python executioner.py -c daily.json --parallel 2>&1 | logger -t executioner

# Run every 4 hours with environment variables
0 */4 * * * cd /opt/monitoring && ENV=prod python executioner.py -c monitoring.json 2>&1 | logger -t monitoring
```

## Best Practices

### Configuration Management

1. **Use Version Control**
   ```bash
   git add config.json
   git commit -m "Update pipeline configuration"
   ```

2. **Environment-Specific Configs**
   ```
   configs/
   ├── development.json
   ├── staging.json
   └── production.json
   ```

3. **Configuration Validation**
   ```bash
   # Always test configurations
   python executioner.py -c config.json --dry-run
   ```

### Error Handling

1. **Implement Proper Retry Logic**
   ```json
   {
     "max_retries": 3,
     "retry_delay": 60,
     "retry_backoff": 2.0,
     "retry_on_exit_codes": [1, 2, 3]
   }
   ```

2. **Use Continue-on-Error Strategically**
   ```bash
   # For non-critical pipelines
   python executioner.py -c config.json --continue-on-error
   ```

3. **Monitor and Alert**
   ```json
   {
     "email_on_failure": true,
     "email_address": ["team@company.com", "oncall@company.com"]
   }
   ```

### Performance Optimization

1. **Use Parallel Execution for Independent Jobs**
   ```bash
   python executioner.py -c config.json --parallel --workers 8
   ```

2. **Set Appropriate Timeouts**
   ```json
   {
     "default_timeout": 3600,
     "jobs": [
       {
         "id": "quick_job",
         "timeout": 300
       },
       {
         "id": "long_job",
         "timeout": 7200
       }
     ]
   }
   ```

3. **Monitor Resource Usage**
   ```bash
   # Use verbose logging to track performance
   python executioner.py -c config.json --verbose
   ```

### Security

1. **Use Environment Variables for Secrets**
   ```bash
   export API_KEY="secret-key"
   python executioner.py -c config.json --env "API_KEY=${API_KEY}"
   ```

2. **Implement Security Policies**
   ```json
   {
     "security_policy": "strict",
     "allow_shell": false
   }
   ```

3. **Limit Shell Environment Inheritance**
   ```json
   {
     "inherit_shell_env": ["PATH", "HOME", "USER"]
   }
   ```

## Troubleshooting

### Common Issues and Solutions

#### Configuration Errors
```bash
# Problem: Invalid JSON syntax
# Solution: Validate JSON format
python -m json.tool config.json

# Problem: Circular dependencies
# Solution: Use dry run to identify cycles
python executioner.py -c config.json --dry-run --verbose
```

#### Execution Problems
```bash
# Problem: Jobs hanging or timing out
# Solution: Check logs and adjust timeouts
tail -f logs/executioner.*.log

# Problem: Environment variable issues
# Solution: Debug environment setup
python executioner.py -c config.json --visible --dry-run
```

#### Resume Issues
```bash
# Problem: Cannot resume from run
# Solution: Check run exists and status
python executioner.py --show-run 123

# Problem: Jobs marked successful incorrectly
# Solution: Check job status before marking
python executioner.py --show-run 123
```

### Debugging Steps

1. **Enable Debug Logging**
   ```bash
   python executioner.py -c config.json --debug
   ```

2. **Check Configuration**
   ```bash
   python executioner.py -c config.json --dry-run --verbose
   ```

3. **Verify Environment**
   ```bash
   python executioner.py -c config.json --visible --dry-run
   ```

4. **Examine Logs**
   ```bash
   tail -f logs/executioner.*.log
   grep ERROR logs/executioner.*.log
   ```

5. **Test Individual Components**
   ```bash
   # Test single job execution
   python test_job.py job_id
   
   # Test database connectivity
   python -c "from db.sqlite_connection import db_connection; print('DB OK')"
   ```

### Performance Troubleshooting

#### Identify Bottlenecks
```bash
# Monitor system resources during execution
top -p $(pgrep -f executioner)

# Check disk I/O
iostat -x 1

# Monitor memory usage
free -h
```

#### Optimize Execution
```bash
# Reduce worker count if system is overloaded
python executioner.py -c config.json --parallel --workers 2

# Use sequential execution for debugging
python executioner.py -c config.json --sequential --debug
```

### Getting Help

1. **Check Logs First**
   - Main execution log: `logs/executioner.{app}.run-{id}.log`
   - Individual job logs: `logs/executioner.{app}.job-{job}.run-{id}.log`

2. **Use Debug Mode**
   ```bash
   python executioner.py -c config.json --debug --dry-run
   ```

3. **Validate Configuration**
   ```bash
   python executioner.py -c config.json --dry-run --verbose
   ```

4. **Check System Requirements**
   - Python 3.6+
   - Sufficient disk space for logs
   - Appropriate file permissions
   - Network connectivity (if required by jobs)