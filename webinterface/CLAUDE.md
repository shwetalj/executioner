* I am developing a visual, and easy to use web interface for executioner workflow orchestraction engine. 
* /home/sjoshi/claudelab/executioner/executioner.py is the python appliaction I am developing this interface for
* The technology stack I would like to use is tailwind CSS and Vue.js. At some point when we are ready for a backend, we will use either Flask or FastAPI
* At first I would like to create an editor that will be able to construct JSON config files that will look like sample configuration below
-  The editor should be able to load existing configuration, or create a new jobs config json file. 
-  It should provide a section for Application config
-  It should also provide + Add Jobs. Jobs can be added and will be populated on the left side of the page.
-  A user will be provided with a config canvas where they can drag and drop jobs that have been created.
- The jobs dropped in the canvas can be linked to each other. For example you can add one job with no dependencies, and subsequent jobs with 1 or more dependencies. You will be generating a DAG
- The whole setup should be very professional, visually appealing and easy to use.
- As jobs are being constructed visually, a user should be able to see the json file being constructed as well. They should be able to modify the json file within this editor and have the changes reflected in the visual setup.

================================================================================
                              SAMPLE CONFIGURATION                              
================================================================================
{
    "application_name": "data_pipeline",
    "default_timeout": 10800,
    "default_max_retries": 2,
    "default_retry_delay": 30,
    "default_retry_backoff": 1.5,
    "default_retry_jitter": 0.1,
    "default_max_retry_time": 1800,
    "default_retry_on_exit_codes": [1],
    "email_address": "alerts@example.com",
    "email_on_success": true,
    "email_on_failure": true,
    "smtp_server": "mail.example.com",
    "smtp_port": 587,
    "smtp_user": "user@example.com",
    "smtp_password": "your-password",
    "parallel": true,
    "max_workers": 3,
    "allow_shell": true,
    "inherit_shell_env": "default",
    "env_variables": {
        "APP_ENV": "production",
        "LOG_LEVEL": "info",
        "DATA_DIR": "/data",
        "BASE_PATH": "/opt/pipeline",
        "CONFIG_PATH": "${BASE_PATH}/config",
        "OUTPUT_PATH": "${BASE_PATH}/output"
    },
    "dependency_plugins": [],
    "security_policy": "warn",
    "log_dir": "./logs",
    "jobs": [
        {
            "id": "download_data",
            "description": "Download raw data",
            "command": "python download_script.py",
            "timeout": 300,
            "env_variables": {
                "API_KEY": "your-api-key",
                "DOWNLOAD_PATH": "${DATA_DIR}/raw"
            },
            "pre_checks": [
                {"name": "check_file_exists", "params": {"path": "/data/raw"}}
            ],
            "post_checks": [
                {"name": "check_no_ora_errors", "params": {"log_file": "./logs/output.log"}}
            ],
            "max_retries": 2,
            "retry_delay": 20,
            "retry_backoff": 2.0,
            "retry_jitter": 0.2,
            "max_retry_time": 600,
            "retry_on_status": ["ERROR", "FAILED", "TIMEOUT"],
            "retry_on_exit_codes": [1, 2]
        },
        {
            "id": "clean_data",
            "description": "Clean downloaded data",
            "command": "python clean_data_script.py",
            "dependencies": ["download_data"],
            "timeout": 600,
            "env_variables": {
                "DEBUG": "true",
                "INPUT_PATH": "${DATA_DIR}/raw",
                "OUTPUT_PATH": "${DATA_DIR}/clean"
            },
            "pre_checks": [
                {"name": "check_file_exists", "params": {"path": "/data/raw"}}
            ],
            "post_checks": [
                {"name": "check_no_ora_errors", "params": {"log_file": "./logs/clean.log"}}
            ]
        },
        {
            "id": "generate_report",
            "description": "Generate report",
            "command": "python generate_report.py --output ${OUTPUT_PATH}/report.pdf",
            "dependencies": ["clean_data"],
            "timeout": 900,
            "env_variables": {
                "REPORT_FORMAT": "pdf",
                "DATA_PATH": "${DATA_DIR}/clean"
            },
            "pre_checks": [],
            "post_checks": []
        }
    ]
}

Configuration Options:
- inherit_shell_env: Control environment inheritance
  - true: inherit all shell variables (backward compatible)
  - false: complete isolation
  - "default": inherit common system variables only
  - ["PATH", "HOME", ...]: custom whitelist
- Environment variables support interpolation: ${VAR_NAME}
- security_policy: "strict" to block potentially unsafe commands
- dependency_plugins: List of Python modules for custom dependencies
- See ENV_ISOLATION_DOCS.md for detailed environment variable documentation
--------------------------------------------------------------------------------

* Executioner CLI interface:

usage: executioner.py [-h] [-c CONFIG] [--sample-config] [--dry-run] [--skip JOB_IDS] [--env ENV] [--continue-on-error] [--parallel] [--workers N] [--sequential] [--resume-from RUN_ID] [--resume-failed-only]
                      [--mark-success] [-r RUN_ID] [-j JOB_IDS] [--list-runs [APP_NAME]] [--show-run RUN_ID] [--debug] [--verbose] [--visible]

Executioner - A robust job execution engine with dependency management, parallel execution, and retry capabilities

options:
  -h, --help            show this help message and exit
  -c CONFIG, --config CONFIG
                        Path to job configuration file (default: jobs_config.json)
  --sample-config       Display a sample configuration file and exit

Execution control:
  --dry-run             Show what would be executed without actually running jobs
  --skip JOB_IDS        Skip specified job IDs (comma-separated or multiple --skip)
  --env ENV             Set environment variables (KEY=value or KEY1=val1,KEY2=val2)

Failure handling:
  --continue-on-error   Continue executing remaining jobs even if a job fails

Parallel execution:
  --parallel            Enable parallel job execution (overrides config setting)
  --workers N           Number of parallel workers (default: from config or 1)
  --sequential          Force sequential execution even if config enables parallel

Resume and recovery:
  --resume-from RUN_ID  Resume execution from a previous run ID
  --resume-failed-only  When resuming, only re-run jobs that failed (skip successful ones)
  --mark-success        Mark specific jobs as successful in a previous run (use with -r and -j)
  -r RUN_ID, --run-id RUN_ID
                        Run ID for --mark-success operation
  -j JOB_IDS, --jobs JOB_IDS
                        Comma-separated job IDs for --mark-success operation

History and reporting:
  --list-runs [APP_NAME]
                        List recent execution history (optionally filtered by app name) and exit
  --show-run RUN_ID     Show detailed job status for a specific run ID

Logging and debugging:
  --debug               Enable debug logging (most detailed output)
  --verbose             Enable verbose logging (INFO level messages)
  --visible             Display all environment variables for each job before execution

Examples:
  executioner.py -c jobs_config.json                    # Basic execution
  executioner.py -c jobs_config.json --dry-run          # Validate without running
  executioner.py -c jobs_config.json --parallel         # Parallel execution
  executioner.py -c jobs_config.json --skip job1,job2   # Skip specific jobs
  executioner.py --resume-from 123                      # Resume from run 123
  executioner.py --list-runs                            # Show execution history
  executioner.py --sample-config                        # Show config example

For detailed documentation, configuration options, and advanced features:
See README.md and docs/ directory in the project repository.


