#!/usr/bin/env python3


"""
Executioner - A job execution engine with dependency support

This module provides a flexible job execution system that reads a JSON configuration file,
resolves job dependencies, and executes jobs in the correct order. It supports features
like job timeout, email notifications, dry run mode, dependency validation, and parallel execution.
"""

import json
import subprocess
import shlex
import threading
import sqlite3
import logging
import sys
import datetime
import os
import re
import smtplib
import socket
import time
import argparse
import ssl
import signal
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from queue import Queue, Empty
from typing import Dict, Set, List, Optional, Any, Tuple
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from pathlib import Path

# Modularized imports
from config.loader import Config
from executioner_logging.setup import ensure_log_dir
from db.sqlite_connection import db_connection, init_db
from config.validator import validate_config
from jobs.executioner import JobExecutioner
from jobs.env_utils import parse_env_vars, substitute_env_vars_in_obj
from jobs.logging_setup import setup_logging

def parse_skip_jobs(skip_list):
    """Parse comma-separated job IDs. Supports both repeated and comma-separated formats."""
    if not skip_list:
        return []
    job_ids = []
    for skip_entry in skip_list:
        # Support comma-separated job IDs in a single argument
        ids = [id.strip() for id in skip_entry.split(',') if id.strip()]
        job_ids.extend(ids)
    # Remove duplicates while preserving order
    seen = set()
    unique_ids = []
    for job_id in job_ids:
        if job_id not in seen:
            seen.add(job_id)
            unique_ids.append(job_id)
    return unique_ids

SIMPLE_CONFIG = """{
    "application_name": "my_pipeline",
    "working_dir": "/home/user/my_pipeline",
    "jobs": [
        {
            "id": "job1",
            "description": "First job - downloads data",
            "command": "python download_data.py"
        },
        {
            "id": "job2",
            "description": "Second job - processes data",
            "command": "python process_data.py",
            "dependencies": ["job1"]
        },
        {
            "id": "job3",
            "description": "Third job - generates report",
            "command": "python generate_report.py",
            "dependencies": ["job2"]
        }
    ]
}

This minimal configuration will:
- Run three jobs in sequence (job1 -> job2 -> job3)
- Use default timeout of 3 hours per job
- Send email notifications on failure (if SMTP is configured)
- Log output to ./logs directory

For more features like parallel execution, retries, and environment variables,
use --sample-config to see a comprehensive example."""

SAMPLE_CONFIG = """{
    "application_name": "data_pipeline",
    "working_dir": "/opt/pipeline",
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
- See ENV_ISOLATION_DOCS.md for detailed environment variable documentation"""

def main():
    epilog_text = """
Examples:
  %(prog)s -c jobs_config.json                    # Basic execution
  %(prog)s -c jobs_config.json --dry-run          # Validate without running
  %(prog)s -c jobs_config.json --parallel         # Parallel execution
  %(prog)s -c jobs_config.json --skip job1,job2   # Skip specific jobs
  %(prog)s --resume-from 123                      # Resume from run 123
  %(prog)s --list-runs                            # Show execution history
  %(prog)s --simple-config                        # Show simple config for beginners
  %(prog)s --sample-config                        # Show comprehensive config example

Advanced Configuration Features (use --sample-config to see all options):
  - Security policies and command whitelisting
  - Retry configuration with backoff, jitter, and exit codes
  - Environment variable interpolation (${VAR_NAME} syntax)
  - Pre/post job validation checks
  - Custom dependency plugins
  - Per-job configuration overrides

For detailed documentation, configuration options, and advanced features:
See README.md and docs/ directory in the project repository.
"""
    parser = argparse.ArgumentParser(
        description="Executioner - A robust job execution engine with dependency management, parallel execution, and retry capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_text
    )
    # Basic configuration
    parser.add_argument("-c", "--config", default="jobs_config.json", help="Path to job configuration file (default: jobs_config.json)")
    parser.add_argument("--simple-config", action="store_true", help="Display a simple, minimal configuration example for getting started")
    parser.add_argument("--sample-config", action="store_true", help="Display a sample configuration file with all available options including security policies, retry settings, environment variables, and more")

    # Execution control options
    execution_group = parser.add_argument_group("Execution control")
    execution_group.add_argument("--dry-run", action="store_true", help="Show what would be executed without actually running jobs")
    execution_group.add_argument("--skip", action='append', metavar="JOB_IDS", help="Skip specified job IDs (comma-separated or multiple --skip)")
    execution_group.add_argument("--env", action='append', help="Set environment variables (KEY=value or KEY1=val1,KEY2=val2)")

    # Failure handling options
    failure_group = parser.add_argument_group("Failure handling")
    failure_group.add_argument("--continue-on-error", action="store_true", help="Continue executing remaining jobs even if a job fails")

    # Parallel execution options
    parallel_group = parser.add_argument_group("Parallel execution")
    parallel_group.add_argument("--parallel", action="store_true", help="Enable parallel job execution (overrides config setting)")
    parallel_group.add_argument("--workers", type=int, metavar="N", help="Number of parallel workers (default: from config or 1)")
    parallel_group.add_argument("--sequential", action="store_true", help="Force sequential execution even if config enables parallel")

    # Resume and recovery options
    resume_group = parser.add_argument_group("Resume and recovery")
    resume_group.add_argument("--resume-from", type=int, metavar="RUN_ID", help="Resume execution from a previous run ID")
    resume_group.add_argument("--resume-failed-only", action="store_true", help="When resuming, only re-run jobs that failed (skip successful ones)")
    resume_group.add_argument("--mark-success", action="store_true", help="Mark specific jobs as successful in a previous run (use with -r and -j)")
    resume_group.add_argument("-r", "--run-id", type=int, metavar="RUN_ID", help="Run ID for --mark-success operation")
    resume_group.add_argument("-j", "--jobs", metavar="JOB_IDS", help="Comma-separated job IDs for --mark-success operation")

    # History and reporting options
    history_group = parser.add_argument_group("History and reporting")
    history_group.add_argument("--list-runs", nargs='?', const=True, metavar="APP_NAME",
                             help="List recent execution history (optionally filtered by app name) and exit")
    history_group.add_argument("--limit", type=int, default=100, metavar="N",
                             help="Number of entries to show with --list-runs (default: 100)")
    history_group.add_argument("--show-run", type=int, metavar="RUN_ID", help="Show detailed job status for a specific run ID")

    # Logging and debugging options
    logging_group = parser.add_argument_group("Logging and debugging")
    logging_group.add_argument("--debug", action="store_true", help="Enable debug logging (most detailed output)")
    logging_group.add_argument("--verbose", action="store_true", help="Enable verbose logging (INFO level messages)")
    logging_group.add_argument("--visible", action="store_true", help="Display all environment variables for each job before execution")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    # Set logging level based on --debug/--verbose
    if args.debug:
        logging_level = logging.DEBUG
    elif args.verbose:
        logging_level = logging.INFO
    else:
        logging_level = logging.WARNING

    # Set up root logger and propagate to all loggers
    logging.basicConfig(level=logging_level)

    # Handle --simple-config flag
    if args.simple_config:
        divider = "=" * 80
        print(f"\n{divider}")
        print(f"{'SIMPLE CONFIGURATION EXAMPLE':^80}")
        print(f"{divider}")
        print(SIMPLE_CONFIG)
        sys.exit(0)

    # Handle --sample-config flag
    if args.sample_config:
        divider = "=" * 80
        print(f"\n{divider}")
        print(f"{'SAMPLE CONFIGURATION':^80}")
        print(f"{divider}")
        print(SAMPLE_CONFIG)
        print("-" * 80)
        print("Copy and modify as needed for your own pipeline.")
        sys.exit(0)

    # Handle --list-runs flag
    if args.list_runs is not None:  # Will be True or a string (app name) when specified
        # Initialize database before querying
        Config.set_log_dir(Path.cwd() / "logs")
        ensure_log_dir()
        init_db(verbose=args.verbose)
        from jobs.execution_history_manager import ExecutionHistoryManager

        # Create a temporary job history manager just for querying
        temp_logger = setup_logging("executioner", "query")
        job_history = ExecutionHistoryManager({}, None, None, temp_logger)

        # Get recent runs, optionally filtered by app name
        app_filter = args.list_runs if isinstance(args.list_runs, str) else None
        limit = getattr(args, 'limit', 100)  # Default to 100 if not specified
        recent_runs = job_history.get_recent_runs(limit=limit, app_name=app_filter)

        if not recent_runs:
            if app_filter:
                print(f"\nNo execution history found for application '{app_filter}'.")
                print("Use --list-runs without an argument to see all runs.")
            else:
                print("\nNo execution history found.")
                print("Run executioner with a config file to create execution history.")
            sys.exit(0)

        # Display the runs
        if app_filter:
            print(f"\nRecent Execution History for '{app_filter}':")
        else:
            print("\nRecent Execution History:")
        print("=" * 110)
        print(f"{'Run':>7} | {'Attempt':>7} | {'Application':20} | {'Status':10} | {'Start Time':19} | {'Duration':>8} | {'Jobs':>12}")
        print("-" * 110)

        for run in recent_runs:
            run_id = run['run_id']
            attempt_id = run.get('attempt_id', 1)  # Default to 1 for old data
            app_name = run['application_name'][:20]
            status = run['status']
            start_time = run['start_time'] or 'N/A'
            duration = run['duration'] or 'N/A'
            job_summary = run['job_summary']
            
            # Format attempt display
            attempt_display = f"#{attempt_id}"

            # Color code status (only if terminal supports it)
            if sys.stdout.isatty() and os.environ.get('TERM') != 'dumb':
                if status == 'SUCCESS':
                    status_display = f"\033[32m{status:10}\033[0m"  # Green
                elif status in ['FAILED', 'ERROR']:
                    status_display = f"\033[31m{status:10}\033[0m"  # Red
                else:
                    status_display = f"\033[33m{status:10}\033[0m"  # Yellow
            else:
                status_display = f"{status:10}"

            print(f"{run_id:>7} | {attempt_display:>7} | {app_name:20} | {status_display} | {start_time:19} | {duration:>8} | {job_summary:>12}")

        print("\nTo resume a failed run: executioner.py -c <config> --resume-from <RUN>")
        print("To resume only failed jobs: executioner.py -c <config> --resume-from <RUN> --resume-failed-only")
        sys.exit(0)

    # Handle --show-run flag
    if args.show_run:
        if args.show_run <= 0:
            print("Error: Run ID must be a positive integer")
            sys.exit(1)
        # Initialize database
        Config.set_log_dir(Path.cwd() / "logs")
        ensure_log_dir()
        init_db(verbose=args.verbose)
        from jobs.execution_history_manager import ExecutionHistoryManager

        # Create job history manager
        temp_logger = setup_logging("executioner", "show-run")
        job_history = ExecutionHistoryManager({}, None, None, temp_logger)

        # Get run details
        run_details = job_history.get_run_details(args.show_run)

        if not run_details:
            print(f"\nError: Run ID {args.show_run} not found.")
            print("Use --list-runs to see available runs.")
            sys.exit(1)

        # Display run header
        run_info = run_details['run_info']
        attempt_id = run_info.get('attempt_id', 1)
        print(f"\nRun Details for ID {args.show_run} (All Attempts):")
        print("=" * 80)
        print(f"Application: {run_info['application_name']}")
        print(f"Total Attempts: {attempt_id}")
        print(f"Final Status: {run_info['status']}")
        print(f"Start Time: {run_info['start_time']}")
        print(f"End Time: {run_info['end_time']}")
        print(f"Duration: {run_info['duration']}")
        print(f"Total Jobs in Config: {run_info['total_jobs']}")

        jobs = run_details['jobs']

        # Group jobs by status
        successful_jobs = [j for j in jobs if j['status'] == 'SUCCESS']
        failed_jobs = [j for j in jobs if j['status'] in ['FAILED', 'ERROR', 'TIMEOUT']]
        skipped_jobs = [j for j in jobs if j['status'] == 'SKIPPED']
        other_jobs = [j for j in jobs if j['status'] not in ['SUCCESS', 'FAILED', 'ERROR', 'TIMEOUT', 'SKIPPED']]

        unique_jobs = len(set(j['id'] for j in jobs))
        total_executions = len(jobs)
        print(f"Unique Jobs Executed: {unique_jobs}")
        print(f"Total Executions: {total_executions}")
        print(f"  - Successful: {len(successful_jobs)}")
        print(f"  - Failed: {len(failed_jobs)}")
        print(f"  - Skipped: {len(skipped_jobs)}")
        
        # Show jobs that ran multiple times
        if total_executions > unique_jobs:
            from collections import Counter
            job_counts = Counter(j['id'] for j in jobs)
            multi_runs = [f"{job_id} ({count}x)" for job_id, count in job_counts.items() if count > 1]
            if multi_runs:
                print(f"Jobs with multiple executions: {', '.join(multi_runs)}")
        # Use stored working directory for log path, fallback to current directory
        if run_info.get('working_dir'):
            log_path = os.path.join(run_info['working_dir'], 'logs', f"executioner.{run_info['application_name']}.run-{args.show_run}.log")
        else:
            # Fallback for older runs without working_dir
            log_path = os.path.abspath(f"./logs/executioner.{run_info['application_name']}.run-{args.show_run}.log")
        print(f"Main log: {log_path}")

        # Display job details in tabular format
        print(f"\nJob Status Details (All Attempts):")
        # Calculate table width: 30 + 3 + 7 + 3 + 8 + 3 + 19 + 3 + 19 + 3 + 8 = 106
        table_width = 106
        print("=" * table_width)
        print(f"{'Job ID':30} | {'Attempt':7} | {'Status':8} | {'Start Time':19} | {'End Time':19} | {'Duration':>8}")
        print("-" * table_width)

        # Display all jobs in tabular format (ordered by execution time)
        for job in jobs:
            # Format duration
            duration_str = "N/A"
            if job.get('duration_seconds') is not None:
                seconds = int(job['duration_seconds'])
                minutes, secs = divmod(seconds, 60)
                hours, mins = divmod(minutes, 60)
                duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

            # Format times
            start_time = job.get('last_run', 'N/A')[:19] if job.get('last_run') else 'N/A'
            end_time = job.get('end_time', 'N/A')[:19] if job.get('end_time') else 'N/A'

            # Truncate job ID if too long
            job_id = job['id'][:29] if len(job['id']) > 29 else job['id']
            attempt_str = f"#{job.get('attempt_id', 1)}"

            print(f"{job_id:30} | {attempt_str:7} | {job['status']:8} | {start_time:19} | {end_time:19} | {duration_str:>8}")

        print()  # Add newline after table

        # Only show failed jobs and resume options if the final status is not SUCCESS
        if run_info['status'] != 'SUCCESS':
            # Display failed job commands if any
            if failed_jobs:
                print(f"\nFailed Job Commands:")
                print("-" * 80)
                for job in failed_jobs:
                    if job.get('command'):
                        print(f"{job['id']}: {job['command']}")

            # Display resume instructions
            if failed_jobs or skipped_jobs:
                print(f"\nResume Options:")
                print("-" * 80)
                # Always use the original run ID for resume commands
                original_run = run_info.get('original_run_id', args.show_run)
                print(f"To continue this workflow:")
                print(f"  executioner.py -c <config> --resume-from {original_run}")
                if failed_jobs:
                    print(f"\nTo retry only failed jobs:")
                    print(f"  executioner.py -c <config> --resume-from {original_run} --resume-failed-only")

                if failed_jobs:
                    failed_job_ids = ','.join([j['id'] for j in failed_jobs])
                    print(f"\nTo mark failed jobs as successful:")
                    print(f"  executioner.py --mark-success -r {args.show_run} -j {failed_job_ids}")
        else:
            # Show completion information for successful runs
            if attempt_id > 1:
                print(f"\n✓ Run completed successfully after {attempt_id} attempts")

        sys.exit(0)

    # Validate run_id if provided
    if args.run_id is not None:
        if args.run_id <= 0:
            print("Error: Run ID must be a positive integer")
            sys.exit(1)

    # Handle --mark-success flag
    if args.mark_success:
        if not args.run_id or not args.jobs:
            print("Error: --mark-success requires both -r RUN_ID and -j JOB_IDS")
            print("Example: executioner.py --mark-success -r 249 -j job1,job2")
            sys.exit(1)

        # Initialize database
        Config.set_log_dir(Path.cwd() / "logs")
        ensure_log_dir()
        init_db(verbose=args.verbose)
        from jobs.execution_history_manager import ExecutionHistoryManager

        # Parse job IDs
        job_ids = [job.strip() for job in args.jobs.split(',')]

        # Create job history manager
        temp_logger = setup_logging("executioner", "mark-success")
        job_history = ExecutionHistoryManager({}, None, None, temp_logger)

        # Get current status of these jobs
        print(f"\nChecking status for run {args.run_id}...")
        current_statuses = job_history.get_job_statuses_for_run(args.run_id, job_ids)

        if not current_statuses:
            print(f"Error: No jobs found for run ID {args.run_id}")
            print("Use --list-runs to see available runs")
            sys.exit(1)

        # Display current status
        print(f"\nCurrent status for run {args.run_id}:")
        for job_id, status in current_statuses.items():
            if job_id in job_ids:
                print(f"  - {job_id}: {status}")
            else:
                print(f"  - {job_id}: NOT FOUND in run")

        # Check which jobs can be marked
        jobs_to_mark = []
        for job_id in job_ids:
            if job_id not in current_statuses:
                print(f"\nWarning: Job '{job_id}' not found in run {args.run_id}")
            elif current_statuses[job_id] == 'SUCCESS':
                print(f"\nInfo: Job '{job_id}' is already marked as SUCCESS")
            elif current_statuses[job_id] in ['FAILED', 'ERROR', 'TIMEOUT']:
                jobs_to_mark.append(job_id)
            else:
                print(f"\nWarning: Job '{job_id}' has status '{current_statuses[job_id]}' - can only mark FAILED/ERROR/TIMEOUT jobs")

        if not jobs_to_mark:
            print("\nNo jobs to mark as successful.")
            sys.exit(0)

        # Confirm action
        print(f"\nWill mark the following jobs as SUCCESS:")
        for job_id in jobs_to_mark:
            print(f"  - {job_id}")

        response = input("\nAre you sure you want to mark these jobs as SUCCESS? [y/N]: ")
        if response.lower() != 'y':
            print("Operation cancelled.")
            sys.exit(0)

        # Mark jobs as successful
        success_count = job_history.mark_jobs_successful(args.run_id, jobs_to_mark)

        if success_count > 0:
            print(f"\n✓ Successfully marked {success_count} job(s) as SUCCESS")
            print(f"Note: Added comment 'Manually marked successful at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}'")
            print(f"\nTo resume the run with dependent jobs:")
            print(f"  executioner.py -c <config> --resume-from {args.run_id}")
        else:
            print("\nError: Failed to update job status")
            sys.exit(1)

        sys.exit(0)

    # Load config file and set log dir BEFORE init_db or JobExecutioner
    try:
        with open(args.config, 'r') as f:
            config_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{args.config}' not found.")
        print(f"Please check the file path or create the configuration file.")
        print(f"Use --sample-config to see an example configuration.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in configuration file '{args.config}'.")
        print(f"JSON error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading configuration file '{args.config}': {e}")
        sys.exit(1)

    # Handle working directory - must be done before setting log directory
    # working_dir is now mandatory - validate early
    if "working_dir" not in config_data:
        print("Error: Configuration is missing required 'working_dir' field")
        print("Please add a 'working_dir' field with an absolute path to your config file.")
        print("Example: \"working_dir\": \"/home/user/project\"")
        print("Use --sample-config to see a complete example configuration.")
        sys.exit(1)

    working_dir = Path(config_data["working_dir"]).expanduser().resolve()

    # Change to working directory
    original_cwd = Path.cwd()
    try:
        os.chdir(working_dir)
        if args.verbose or args.debug:
            print(f"Changed working directory to: {working_dir}")
    except Exception as e:
        print(f"Error: Cannot change to working directory '{working_dir}': {e}")
        sys.exit(1)

    # Store working directory for database
    resolved_working_dir = str(working_dir)

    if "log_dir" in config_data:
        # If log_dir is relative, it's now relative to working_dir
        Config.set_log_dir(config_data["log_dir"])
    else:
        Config.set_log_dir(Path.cwd() / "logs")
    ensure_log_dir()

    init_db(verbose=args.verbose)
    executioner = JobExecutioner(args.config, resolved_working_dir)

    # Store original job-level envs for each job before merging
    original_job_envs = {job_id: dict(job.get("env_variables", {})) for job_id, job in executioner.jobs.items()}

    # Parse CLI envs if provided
    env_vars = parse_env_vars(args.env, debug=args.debug) if args.env else {}

    # Store CLI environment variables in executioner for later use
    executioner.cli_env_variables = env_vars

    # Show merged environment for each job
    if args.visible or args.debug:
        print("\n===== Environment Variables for Each Job (Precedence: CLI > Job > Application) =====")
        for job_id, job in executioner.jobs.items():
            merged_env = dict(executioner.app_env_variables)
            merged_env.update(original_job_envs.get(job_id, {}))
            if args.env:
                merged_env.update(env_vars)
            print(f"\nJob: {job_id}")
            for k, v in merged_env.items():
                print(f"  {k}={v}")
        print("===============================================================================\n")
    elif args.verbose:
        # Print a summary only
        job_count = len(executioner.jobs)
        print(f"\n[INFO] {job_count} jobs loaded. Showing environment variables for the first job only (use --visible for all):")
        first_job_id = next(iter(executioner.jobs))
        merged_env = dict(executioner.app_env_variables)
        merged_env.update(original_job_envs.get(first_job_id, {}))
        if args.env:
            merged_env.update(env_vars)
        print(f"\nJob: {first_job_id}")
        for k, v in merged_env.items():
            print(f"  {k}={v}")
        if job_count > 1:
            print(f"...and {job_count-1} more jobs. Use --visible to see all.")
        print("===============================================================================\n")

    if args.sequential:
        executioner.parallel = False
        executioner.execution_orchestrator.parallel = False
        executioner.logger.info("Parallel execution disabled")
    elif args.parallel:
        executioner.parallel = True
        executioner.execution_orchestrator.parallel = True
        executioner.logger.info("Parallel execution enabled")
        # If parallel is enabled and no explicit workers set, use the config default
        if args.workers is None:
            executioner.logger.info(f"Using {executioner.max_workers} workers from config")

        # Override workers if specified on command line
        # If parallel is enabled and no explicit workers set, use the config default
        if args.workers is None:
            executioner.logger.info(f"Using {executioner.max_workers} workers from config")

    # Override workers if specified on command line
    if args.workers is not None and args.workers > 0:
        executioner.max_workers = args.workers
        executioner.execution_orchestrator.max_workers = args.workers
        executioner.logger.info(f"Set workers to {args.workers}")

    if args.resume_failed_only and args.resume_from is None:
        parser.error("--resume-failed-only requires --resume-from")

    if args.resume_from is not None:
        if args.resume_from <= 0:
            print("Error: Resume run ID must be a positive integer")
            sys.exit(1)

    # Parse skip jobs if provided
    skip_jobs = parse_skip_jobs(args.skip) if args.skip else []

    try:
        code = executioner.run(
            continue_on_error=args.continue_on_error,
            dry_run=args.dry_run,
            skip_jobs=skip_jobs,
            resume_run_id=args.resume_from,
            resume_failed_only=args.resume_failed_only
        )
        sys.exit(code)
    except KeyboardInterrupt:
        if args.dry_run:
            print("\nDry run interrupted. Exiting...")
            sys.exit(0)
        print("\nExecution interrupted. Shutting down...")
        sys.exit(1)

if __name__ == "__main__":
    main()

