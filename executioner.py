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

def parse_env_vars(env_list):
    """Parse KEY=value environment variables."""
    if not env_list:
        return {}
    env_dict = {}
    for env_var in env_list:
        try:
            key, value = env_var.split('=', 1)
            if not key or not value:
                raise ValueError
            env_dict[key] = value
        except ValueError:
            print(f"Warning: Skipping invalid environment variable: {env_var}")
    return env_dict

SAMPLE_CONFIG = """{
    "application_name": "data_pipeline",
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
            }
        },
        {
            "id": "clean_data",
            "description": "Clean downloaded data",
            "command": "python clean_data_script.py",
            "dependencies": ["download_data"],
            "timeout": 600,
            "env_variables": {
                "DEBUG": "true"
            }
        },
        {
            "id": "generate_report",
            "description": "Generate report",
            "command": "python generate_report.py",
            "dependencies": ["clean_data"],
            "timeout": 900
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
  %(prog)s -c jobs_config.json --parallel --workers 4
  %(prog)s -c jobs_config.json --resume-from 123
  %(prog)s -c jobs_config.json --resume-from 123 --resume-failed-only
  %(prog)s --sample-config        # Shows sample configuration format

Notes:
- Set 'allow_shell: false' in the config to disable shell=True for security.
- Use SMTP authentication by specifying smtp_user and smtp_password.
- Environment variables: Command-line > job-specific > application-level.
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
    parser.add_argument("--env", nargs='+', help="Environment variables (KEY=value)")
    parser.add_argument("--sample-config", action="store_true", help="Display a sample configuration file and exit")
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
    
    # Handle --sample-config flag
    if args.sample_config:
        print("Sample Configuration:")
        print(SAMPLE_CONFIG)
        sys.exit(0)
        
    init_db()
    executioner = JobExecutioner(args.config)

    if args.env:
        env_vars = parse_env_vars(args.env)
        if env_vars:
            for job_id, job in executioner.jobs.items():
                job["env_variables"] = job.get("env_variables", {})
                job["env_variables"].update(env_vars)
            print(f"Environment variables applied: {list(env_vars.keys())}")
            executioner.logger.info(f"Command-line environment variables: {list(env_vars.keys())}")

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
