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
from db.sqlite_backend import db_connection, init_db
from config.validator import validate_config
from jobs.executioner import JobExecutioner
from jobs.env_utils import parse_env_vars, substitute_env_vars_in_obj

SAMPLE_CONFIG = """{
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
    "env_variables": {
        "APP_ENV": "production",
        "LOG_LEVEL": "info",
        "DATA_DIR": "/data"
    },
    "jobs": [
        {
            "id": "download_data",
            "description": "Download raw data",
            "command": "python download_script.py",
            "timeout": 300,
            "env_variables": {
                "API_KEY": "your-api-key",
                "DOWNLOAD_PATH": "/data/raw"
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
                "DEBUG": "true"
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
            "command": "python generate_report.py",
            "dependencies": ["clean_data"],
            "timeout": 900,
            "pre_checks": [],
            "post_checks": []
        }
    ]
}"""

def main():
    epilog_text = """
Examples:
  %(prog)s -c jobs_config.json
  %(prog)s -c jobs_config.json --continue-on-error
  %(prog)s -c jobs_config.json --dry-run
  %(prog)s -c jobs_config.json --skip job1 job2
  %(prog)s -c jobs_config.json --env KEY1=value1 KEY2=value2
  %(prog)s -c jobs_config.json --env DB=prod,LOG_LEVEL=debug
  %(prog)s -c jobs_config.json --parallel --workers 4
  %(prog)s -c jobs_config.json --resume-from 123
  %(prog)s -c jobs_config.json --resume-from 123 --resume-failed-only
  %(prog)s --sample-config        # Shows sample configuration format

Notes:
- Default config file: jobs_config.json (if -c not specified)
- Set 'allow_shell: false' in config to disable shell execution (more secure)
- Use 'smtp_*' settings in config for email authentication
- Environment variable precedence: CLI > job-level > application-level
- CLI env formats: --env KEY=VAL or --env KEY1=VAL1,KEY2=VAL2
- Logs are stored in ./logs/ directory with automatic rotation
- Use --parallel in config or CLI for concurrent job execution
- Use --dry-run to validate config and see execution plan
"""
    parser = argparse.ArgumentParser(
        description="Executioner - A robust job execution engine with dependency management, parallel execution, and retry capabilities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_text
    )
    parser.add_argument("-c", "--config", default="jobs_config.json", help="Path to job configuration file (default: jobs_config.json)")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue executing remaining jobs even if a job fails")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be executed without actually running jobs")
    parser.add_argument("--skip", nargs='+', metavar="JOB_ID", help="Skip specified job IDs during execution")
    parser.add_argument("--env", action='append', help="Set environment variables (KEY=value or KEY1=val1,KEY2=val2)")
    parser.add_argument("--sample-config", action="store_true", help="Display a sample configuration file and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging (most detailed output)")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (INFO level messages)")
    parser.add_argument("--visible", action="store_true", help="Display all environment variables for each job before execution")
    parallel_group = parser.add_argument_group("Parallel execution options")
    parallel_group.add_argument("--parallel", action="store_true", help="Enable parallel job execution (overrides config setting)")
    parallel_group.add_argument("--workers", type=int, metavar="N", help="Number of parallel workers (default: from config or 1)")
    parallel_group.add_argument("--sequential", action="store_true", help="Force sequential execution even if config enables parallel")
    resume_group = parser.add_argument_group("Resume options")
    resume_group.add_argument("--resume-from", type=int, metavar="RUN_ID", help="Resume execution from a previous run ID")
    resume_group.add_argument("--resume-failed-only", action="store_true", help="When resuming, only re-run jobs that failed (skip successful ones)")

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
        
    if "log_dir" in config_data:
        Config.set_log_dir(config_data["log_dir"])
    else:
        Config.set_log_dir(Path.cwd() / "logs")
    ensure_log_dir()

    init_db(verbose=args.verbose)
    executioner = JobExecutioner(args.config)

    # Store original job-level envs for each job before merging
    original_job_envs = {job_id: dict(job.get("env_variables", {})) for job_id, job in executioner.jobs.items()}

    # Parse CLI envs if provided
    env_vars = parse_env_vars(args.env, debug=args.debug) if args.env else {}

    # Always perform substitution for every job, merging app-level, job-level, and CLI envs
    for job_id, job in executioner.jobs.items():
        merged_envs = dict(executioner.app_env_variables)
        merged_envs.update(original_job_envs.get(job_id, {}))
        merged_envs.update(env_vars)
        job["env_variables"] = merged_envs
        executioner.jobs[job_id] = substitute_env_vars_in_obj(job, merged_envs)

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
        executioner.logger.info("Parallel execution disabled")
    elif args.parallel:
        executioner.parallel = True
        executioner.logger.info("Parallel execution enabled")
    if args.workers is not None and args.workers > 0:
        executioner.max_workers = args.workers
        executioner.logger.info(f"Set workers to {args.workers}")

    if args.resume_failed_only and args.resume_from is None:
        parser.error("--resume-failed-only requires --resume-from")

    try:
        code = executioner.run(
            continue_on_error=args.continue_on_error,
            dry_run=args.dry_run,
            skip_jobs=args.skip,
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
