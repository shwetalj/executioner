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

# Ensure log directory is created securely
ensure_log_dir()

def parse_env_vars(env_list, debug=False):
    """Parse KEY=value environment variables. Supports both repeated and comma-separated formats."""
    if debug:
        print(f"DEBUG: parse_env_vars input env_list = {env_list}")
    if not env_list:
        return {}
    env_dict = {}
    for env_entry in env_list:
        # Support comma-separated pairs in a single argument
        pairs = [p.strip() for p in env_entry.split(',') if p.strip()]
        for env_var in pairs:
            try:
                key, value = env_var.split('=', 1)
                if not key or not value:
                    raise ValueError
                env_dict[key] = value
            except ValueError:
                print(f"Warning: Skipping invalid environment variable: {env_var}")
    if debug:
        print(f"DEBUG: parse_env_vars output env_dict = {env_dict}")
    return env_dict

def substitute_env_vars_in_obj(obj, env_vars):
    """
    Recursively substitute ${VAR} in strings within obj using env_vars dict.
    """
    pattern = re.compile(r'\${([A-Za-z_][A-Za-z0-9_]*)}')
    if isinstance(obj, dict):
        return {k: substitute_env_vars_in_obj(v, env_vars) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_env_vars_in_obj(item, env_vars) for item in obj]
    elif isinstance(obj, str):
        def replacer(match):
            var = match.group(1)
            if var in env_vars:
                return env_vars[var]
            else:
                print(f"Warning: No value found for variable: {var}")
                return match.group(0)  # Leave as-is
        return pattern.sub(replacer, obj)
    else:
        return obj

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
    epilog_text = f"""
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
- Set 'allow_shell: false' in the config to disable shell=True for security.
- Use SMTP authentication by specifying smtp_user and smtp_password.
- Environment variables: Command-line > job-specific > application-level.
- You can supply CLI envs as --env KEY=VAL or --env KEY=VAL,KEY2=VAL2 (CSV).
- Logs are stored in {Config.LOG_DIR} with rotation.
- Use --sample-config to see a sample configuration file.
"""
    parser = argparse.ArgumentParser(
        description="Enhanced Job Execution Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=epilog_text
    )
    parser.add_argument("-c", "--config", default="jobs_config.json", help="Path to job configuration file")
    parser.add_argument("--continue-on-error", action="store_true", help="Continue on job failure")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution")
    parser.add_argument("--skip", nargs='+', help="Job IDs to skip")
    parser.add_argument("--env", action='append', help="Environment variables (KEY=value or KEY=value,KEY2=value2; CLI overrides config)")
    parser.add_argument("--sample-config", action="store_true", help="Display a sample configuration file and exit")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging and extra troubleshooting output")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging (INFO level)")
    parser.add_argument("--visible", action="store_true", help="Show environment variables applied to jobs on screen")
    parallel_group = parser.add_argument_group("Parallel execution options")
    parallel_group.add_argument("--parallel", action="store_true", help="Enable parallel execution")
    parallel_group.add_argument("--workers", type=int, metavar="N", help="Number of parallel workers")
    parallel_group.add_argument("--sequential", action="store_true", help="Force sequential execution")
    resume_group = parser.add_argument_group("Resume options")
    resume_group.add_argument("--resume-from", type=int, metavar="RUN_ID", help="Resume from run ID")
    resume_group.add_argument("--resume-failed-only", action="store_true", help="Re-run only failed jobs")

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
        
    init_db(verbose=args.verbose)
    executioner = JobExecutioner(args.config)

    # Store original job-level envs for each job before merging
    original_job_envs = {job_id: dict(job.get("env_variables", {})) for job_id, job in executioner.jobs.items()}

    if args.env:
        env_vars = parse_env_vars(args.env, debug=args.debug)
        if env_vars:
            for job_id, job in executioner.jobs.items():
                job["env_variables"] = job.get("env_variables", {})
                job["env_variables"].update(env_vars)
                # Perform variable substitution in all job fields using merged envs
                merged_envs = job["env_variables"]
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
