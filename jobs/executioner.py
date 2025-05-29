import json
import subprocess
import shlex
import threading
import logging
import sys
import datetime
import os
import re
import glob

import smtplib
import socket
import time
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
import sqlite3

from config.loader import Config
from db.sqlite_backend import db_connection
from config.validator import validate_config
from jobs.checks import CHECK_REGISTRY  # Ensure visibility in all contexts
from jobs.job_runner import JobRunner
from jobs.logger_factory import setup_logging, setup_job_logger
from jobs.job_history_manager import JobHistoryManager
from jobs.dependency_manager import DependencyManager

from jobs.notification_manager import NotificationManager
from jobs.command_utils import validate_command, parse_command
from jobs.env_utils import merge_env_vars, interpolate_env_vars, filter_shell_env
from jobs.queue_manager import QueueManager
from jobs.state_manager import StateManager
from jobs.job_executor import JobExecutor

class JobExecutioner:
    def __init__(self, config_file: str):
        # Store the config file path for later use
        self.config_file = config_file
        # Set up a minimal logger for early errors
        # self.logger = logging.getLogger('executioner')
        # self.logger.handlers.clear()
        # self.logger.addHandler(logging.StreamHandler(sys.stdout))
        # self.logger.setLevel(logging.INFO)
        # self.logger.propagate = False
        # Load and validate configuration
        try:
            with open(str(config_file), "r") as file:
                self.config = json.load(file)
        except FileNotFoundError:
            print(f"Configuration file '{config_file}' not found.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Configuration file '{config_file}' contains invalid JSON: {e}")
            sys.exit(1)
        # Initialize necessary attributes for logging setup
        self.application_name = self.config.get("application_name",
            os.path.splitext(os.path.basename(config_file))[0])
        
        # Validate configuration schema before accessing jobs
        # Use a temporary logger for validation errors
        temp_logger = setup_logging(self.application_name, "main")
        validate_config(self.config, temp_logger)
        try:
            self.jobs: Dict[str, Dict] = {job["id"]: job for job in self.config["jobs"]}
        except KeyError:
            temp_logger.error("Configuration is missing required 'jobs' list.")
            sys.exit(1)
        if len(self.jobs) != len(self.config["jobs"]):
            print("Duplicate job IDs found in configuration")
            sys.exit(1)
        
        # Initialize JobHistoryManager and StateManager
        self.job_history = JobHistoryManager(self.jobs, self.application_name, None, temp_logger)
        self.state_manager = StateManager(self.jobs, self.application_name, self.job_history, temp_logger)
        
        # Initialize run and set up logger with run_id
        self.run_id = self.state_manager.initialize_run()
        self.logger = setup_logging(self.application_name, self.run_id)
        self.job_history.set_logger(self.logger)
        
        # Email notification settings
        self.email_address = self.config.get("email_address", "")
        self.email_on_success = self.config.get("email_on_success", False)
        self.email_on_failure = self.config.get("email_on_failure", True)
        self.smtp_server = self.config.get("smtp_server", "localhost")
        self.smtp_port = self.config.get("smtp_port", 587)  # Default to TLS port
        self.smtp_user = self.config.get("smtp_user", "")
        self.smtp_password = self.config.get("smtp_password", "")
        # Notification manager
        self.notification_manager = NotificationManager(
            email_address=self.email_address,
            email_on_success=self.email_on_success,
            email_on_failure=self.email_on_failure,
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            smtp_user=self.smtp_user,
            smtp_password=self.smtp_password,
            application_name=self.application_name,
            logger=self.logger
        )

        # Execution settings
        self.parallel = self.config.get("parallel", False)
        self.max_workers = self.config.get("max_workers", 1)
        self.allow_shell = self.config.get("allow_shell", True)  # New: Control shell execution
        if self.max_workers <= 0:
            self.max_workers = 1

        # Environment variables
        self.app_env_variables = self.config.get("env_variables", {})
        # Interpolate application-level environment variables
        self.app_env_variables = interpolate_env_vars(self.app_env_variables, self.logger)
        self.cli_env_variables = {}  # Will be set by main executioner
        
        # Shell environment inheritance setting (default to True for backward compatibility)
        self.inherit_shell_env = self.config.get("inherit_shell_env", True)
        self.shell_env = filter_shell_env(self.inherit_shell_env, self.logger)
        
        # Handle dependency plugins if specified
        self.dependency_plugins = self.config.get("dependency_plugins", [])
        
        # Job and dependency setup
        self.jobs: Dict[str, Dict] = {job["id"]: job for job in self.config["jobs"]}
        if len(self.jobs) != len(self.config["jobs"]):
            self.logger.error("Duplicate job IDs found in configuration")
            sys.exit(1)
        self.dependency_manager = DependencyManager(self.jobs, self.logger, self.config.get("dependency_plugins", []))

        # Initialize queue manager for job state and queue operations
        self.queue_manager = QueueManager(self.dependency_manager, self.logger)
        
        # Update state manager with logger
        self.state_manager.logger = self.logger
        
        # Initialize job executor for individual job execution
        self.job_executor = JobExecutor(
            config=self.config,
            app_env_variables=self.app_env_variables,
            cli_env_variables=self.cli_env_variables,
            shell_env=self.shell_env,
            application_name=self.application_name,
            run_id=self.run_id,
            main_logger=self.logger,
            job_history_manager=self.job_history,
            setup_job_logger_func=self._setup_job_logger
        )
        
        # Threading primitives (kept for backward compatibility and executor management)
        self.lock = self.queue_manager.lock  # Use queue manager's lock
        self.job_completed_condition = self.queue_manager.job_completed_condition
        self.executor = None

        # Validate dependencies
        if self.dependency_manager.has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            print(f"{Config.COLOR_RED}ERROR: Circular dependencies detected{Config.COLOR_RESET}")
            sys.exit(1)
        if self.dependency_manager.report_missing_dependencies(self.logger):
            sys.exit(1)

        self.job_log_paths = {}  # Track job log file paths

    # Properties for backward compatibility - delegate to queue manager
    @property
    def job_queue(self) -> Queue:
        """Access to the job queue."""
        return self.queue_manager.job_queue
    
    @property
    def completed_jobs(self) -> Set[str]:
        """Access to completed jobs set."""
        return self.queue_manager.completed_jobs
    
    @property
    def failed_jobs(self) -> Set[str]:
        """Access to failed jobs set."""
        return self.queue_manager.failed_jobs
    
    @property
    def failed_job_reasons(self) -> Dict[str, str]:
        """Access to failed job reasons."""
        return self.queue_manager.failed_job_reasons
    
    @property
    def queued_jobs(self) -> Set[str]:
        """Access to queued jobs set."""
        return self.queue_manager.queued_jobs
    
    @property
    def active_jobs(self) -> Set[str]:
        """Access to active jobs set."""
        return self.queue_manager.active_jobs
    
    @property
    def future_to_job_id(self) -> Dict[Future, str]:
        """Access to future-to-job-id mapping."""
        return self.queue_manager.future_to_job_id
    
    @property
    def skip_jobs(self) -> Set[str]:
        """Access to skip jobs set."""
        return self.queue_manager.skip_jobs
    
    @skip_jobs.setter
    def skip_jobs(self, value: Set[str]) -> None:
        """Set skip jobs."""
        self.queue_manager.set_skip_jobs(value)
    
    # Properties for backward compatibility - delegate to state manager
    @property
    def exit_code(self) -> int:
        """Access to exit code."""
        return self.state_manager.exit_code
    
    @exit_code.setter
    def exit_code(self, value: int) -> None:
        """Set exit code."""
        self.state_manager.set_exit_code(value)
    
    @property
    def start_time(self) -> Optional[datetime.datetime]:
        """Access to start time."""
        return self.state_manager.start_time
    
    @start_time.setter
    def start_time(self, value: Optional[datetime.datetime]) -> None:
        """Set start time."""
        self.state_manager.start_time = value
    
    @property
    def end_time(self) -> Optional[datetime.datetime]:
        """Access to end time."""
        return self.state_manager.end_time
    
    @end_time.setter
    def end_time(self, value: Optional[datetime.datetime]) -> None:
        """Set end time."""
        self.state_manager.end_time = value
    
    @property
    def continue_on_error(self) -> bool:
        """Access to continue on error flag."""
        return self.state_manager.continue_on_error
    
    @continue_on_error.setter
    def continue_on_error(self, value: bool) -> None:
        """Set continue on error flag."""
        self.state_manager.continue_on_error = value
    
    @property
    def dry_run(self) -> bool:
        """Access to dry run flag."""
        return self.state_manager.dry_run
    
    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        """Set dry run flag."""
        self.state_manager.dry_run = value
    
    @property
    def interrupted(self) -> bool:
        """Access to interrupted flag."""
        return self.state_manager.interrupted
    
    @interrupted.setter
    def interrupted(self, value: bool) -> None:
        """Set interrupted flag."""
        if value:
            self.state_manager.mark_interrupted()
        else:
            self.state_manager.interrupted = value

    def _validate_config(self):
        """Validate configuration against a basic schema."""
        if "jobs" not in self.config or not isinstance(self.config["jobs"], list):
            self.logger.error("Configuration is missing required 'jobs' list or 'jobs' is not a list")
            sys.exit(1)

        for i, job in enumerate(self.config["jobs"]):
            if not isinstance(job, dict):
                self.logger.error(f"Job at index {i} is not a dictionary")
                sys.exit(1)
            if "id" not in job or not isinstance(job["id"], str):
                self.logger.error(f"Job at index {i} is missing or has invalid 'id' field")
                sys.exit(1)
            if "command" not in job or not isinstance(job["command"], str):
                self.logger.error(f"Job '{job.get('id', f'at index {i}')}' is missing or has invalid 'command' field")
                sys.exit(1)
            if "timeout" in job and (not isinstance(job["timeout"], (int, float)) or job["timeout"] <= 0):
                self.logger.warning(f"Job '{job['id']}' has invalid timeout: {job['timeout']}. Using default.")
                job["timeout"] = Config.DEFAULT_TIMEOUT
            if "env_variables" in job and not isinstance(job["env_variables"], dict):
                self.logger.error(f"Job '{job['id']}' has invalid env_variables")
                sys.exit(1)
            if "dependencies" in job and not isinstance(job["dependencies"], list):
                self.logger.error(f"Job '{job['id']}' has invalid dependencies")
                sys.exit(1)

    def _setup_job_logger(self, job_id: str) -> Tuple[logging.Logger, logging.FileHandler, str]:
        job = self.jobs[job_id]
        job_log_dir = job.get("log_dir", Config.LOG_DIR)
        os.makedirs(job_log_dir, exist_ok=True)
        job_log_path = os.path.join(job_log_dir, f"executioner.{self.application_name}.job-{job_id}.run-{self.run_id}.log")
        job_logger, job_file_handler = setup_job_logger(self.application_name, self.run_id, job_id, job_log_path)
        job_description = job.get('description', '')
        job_command = job['command']
        job_logger.info(f"Executing job - {job_id}: {job_command}")
        self.job_log_paths[job_id] = job_log_path  # Store the job log path
        return job_logger, job_file_handler, job_log_path

    def _validate_timeout(self, timeout, logger=None):
        if timeout is not None:
            try:
                timeout = int(timeout)
                if timeout <= 0:
                    if logger:
                        logger.warning(f"Invalid timeout value: {timeout}. Using default of 600 seconds.")
                    timeout = 600
            except (ValueError, TypeError):
                if logger:
                    logger.warning(f"Non-numeric timeout value: {timeout}. Using default of 600 seconds.")
                timeout = 600
        return timeout

    def _run_subprocess_command(self, command: str, job_id: str, job_logger: logging.Logger, timeout: int) -> bool:
        """Execute a subprocess command (delegated to JobExecutor)."""
        return self.job_executor.run_subprocess_command(command, job_id, job_logger, timeout)

    def _terminate_process(self, process: subprocess.Popen, job_logger: logging.Logger):
        """Terminate a process (delegated to JobExecutor)."""
        self.job_executor._terminate_process(process, job_logger)

    def _execute_job(self, job_id: str, return_reason: bool = True):
        job = self.jobs[job_id]
        runner = JobRunner(
            job_id=job_id,
            job_config=job,
            global_env=self.app_env_variables,
            main_logger=self.logger,
            config=self.config,
            run_id=self.run_id,
            app_name=self.application_name,
            db_connection=db_connection,
            validate_timeout=self._validate_timeout,
            update_job_status=self.job_history.update_job_status,
            update_retry_history=self.job_history.update_retry_history,
            get_last_exit_code=self.job_history.get_last_exit_code,
            setup_job_logger=self._setup_job_logger,
            cli_env=self.cli_env_variables,
            shell_env=self.shell_env
        )
        runner.job_history = self.job_history
        result, fail_reason = runner.run(dry_run=self.dry_run, continue_on_error=self.continue_on_error, return_reason=True)
        return result, fail_reason

    def _run_dry(self, resume_run_id=None, resume_failed_only=False):
        self.start_time = datetime.datetime.now()
        self.logger.info(f"Starting dry run - printing execution plan")
        if resume_run_id:
            previous_job_statuses = self.job_history.get_previous_run_status(resume_run_id)
            if not previous_job_statuses:
                self.logger.error(f"No job history found for run ID {resume_run_id}. Showing full plan.")
            else:
                resume_mode = "failed jobs only" if resume_failed_only else "all incomplete jobs"
                self.logger.info(f"Resuming from run ID {resume_run_id} ({resume_mode})")
                for job_id, status in previous_job_statuses.items():
                    if job_id not in self.jobs:
                        continue
                    if status == "SUCCESS":
                        self.skip_jobs.add(job_id)
                        self.completed_jobs.add(job_id)
                        self.logger.info(f"Would skip previously successful job: {job_id}")
                    elif resume_failed_only and status in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.logger.info(f"Would re-run previously failed job: {job_id}")
                    elif not resume_failed_only and status not in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.skip_jobs.add(job_id)
                        self.completed_jobs.add(job_id)
                        self.logger.info(f"Would skip job with status {status}: {job_id}")
        if self.dependency_manager.has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            print(f"{Config.COLOR_RED}ERROR: Circular dependencies detected{Config.COLOR_RESET}")
            sys.exit(1)
        missing_dependencies = self.dependency_manager.check_missing_dependencies()
        if missing_dependencies:
            for job_id, missing_deps in missing_dependencies.items():
                msg = f"Job '{job_id}' has missing dependencies: {', '.join(missing_deps)}"
                self.logger.error(msg)
                print(f"{Config.COLOR_RED}ERROR: {msg}{Config.COLOR_RESET}")
            if not self.continue_on_error:
                self.logger.error("Missing dependencies detected. Would abort.")
                print(f"{Config.COLOR_RED}ERROR: Missing dependencies detected{Config.COLOR_RESET}")
                return 1
            print(f"{Config.COLOR_YELLOW}WARNING: Missing dependencies detected but would continue{Config.COLOR_RESET}")
        parallel_text = f"{Config.COLOR_CYAN}Execution mode:{Config.COLOR_RESET} "
        parallel_text += f"{Config.COLOR_MAGENTA}PARALLEL with {self.max_workers} workers{Config.COLOR_RESET}" if self.parallel else f"{Config.COLOR_BLUE}SEQUENTIAL{Config.COLOR_RESET}"
        print(f"\n{parallel_text}")
        if self.app_env_variables:
            app_env_vars = sorted(self.app_env_variables.keys())
            print(f"\n{Config.COLOR_CYAN}Application environment variables:{Config.COLOR_RESET}")
            print(f"{Config.COLOR_MAGENTA}{', '.join(app_env_vars)}{Config.COLOR_RESET}")
        print(f"\n{Config.COLOR_CYAN}Job execution order:{Config.COLOR_RESET}")
        execution_order = self.dependency_manager.get_execution_order()
        for i, job_id in enumerate(execution_order):
            job = self.jobs[job_id]
            job_desc = job.get("description", "")
            env_vars_info = f" {Config.COLOR_MAGENTA}[ENV: {', '.join(job['env_variables'].keys())}]{Config.COLOR_RESET}" if job.get("env_variables") else ""
            deps_info = f" {Config.COLOR_CYAN}[DEPS: {', '.join(self.dependency_manager.get_job_dependencies(job_id)) or 'none'}]{Config.COLOR_RESET}"
            if job_id in self.skip_jobs:
                print(f"{i+1}. {Config.COLOR_YELLOW}{job_id}{Config.COLOR_RESET} - {job_desc} {Config.COLOR_YELLOW}[SKIPPED]{Config.COLOR_RESET}{env_vars_info}{deps_info}")
            else:
                command = job["command"]
                command_preview = command[:40] + '...' if len(command) > 40 else command
                print(f"{i+1}. {Config.COLOR_DARK_GREEN}{job_id}{Config.COLOR_RESET} - {job_desc} - {Config.COLOR_BLUE}{command_preview}{Config.COLOR_RESET}{env_vars_info}{deps_info}")
        self.end_time = datetime.datetime.now()
        duration = self.end_time - self.start_time
        duration_str = str(duration).split('.')[0]
        end_date = self.end_time.strftime("%Y-%m-%d %H:%M:%S")
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"\n{divider}")
        print(f"{Config.COLOR_CYAN}{'DRY RUN EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {self.run_id}")
        start_time_str = self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else "N/A"
        end_time_str = self.end_time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {start_time_str}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_time_str}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} {duration_str}")
        print(f"{Config.COLOR_CYAN}Total Jobs:{Config.COLOR_RESET} {len(self.jobs)}")
        print(f"{Config.COLOR_CYAN}Would Execute:{Config.COLOR_RESET} {Config.COLOR_DARK_GREEN}{len(self.jobs) - len(self.skip_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Would Skip:{Config.COLOR_RESET} {Config.COLOR_YELLOW if len(self.skip_jobs) > 0 else ''}{len(self.skip_jobs)}{Config.COLOR_RESET}")
        print(f"{divider}")
        print("\n")
        self.logger.info(f"Dry run completed for run ID: {self.run_id}")
        return 0

    def _get_execution_order(self):
        order = []
        visited = set()
        temp_visited = set()
        def visit(node):
            if node in temp_visited or node in visited:
                return
            temp_visited.add(node)
            for dep in self.dependency_manager.get_job_dependencies(node):
                if dep in self.jobs:
                    visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            order.append(node)
        for job_id in self.jobs:
            if job_id not in visited:
                visit(job_id)
        return order

    def run(self, continue_on_error: bool = False, dry_run: bool = False, skip_jobs: list = None, max_iter: int = 1000, resume_run_id: int = None, resume_failed_only: bool = False):
        # Load dependency plugins at the start of run(), before printing execution banner
        if self.dependency_plugins:
            self.logger.info(f"Found {len(self.dependency_plugins)} dependency plugins to load")
            self.dependency_manager.load_dependency_plugins()
        # Set initial state through state manager
        self.state_manager.start_execution(continue_on_error, dry_run)
        self.skip_jobs = set(skip_jobs or [])
        divider = f"{Config.COLOR_CYAN}{'='*90}{Config.COLOR_RESET}"
        dry_run_text = " [DRY RUN]" if dry_run else ""
        parallel_text = f" [PARALLEL: {self.max_workers} workers]" if self.parallel else " [SEQUENTIAL]"
        if dry_run:
            try:
                return self._run_dry(resume_run_id, resume_failed_only)
            except KeyboardInterrupt:
                self.logger.info("Dry run interrupted by user")
                print("\nDry run interrupted by user")
                return 0
        if self.dependency_manager.has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            self.exit_code = 1
            self._print_abort_summary("FAILED", reason="Circular dependencies detected")
            return self.exit_code
        missing_dependencies = self.dependency_manager.check_missing_dependencies()
        if missing_dependencies:
            for job_id, missing_deps in missing_dependencies.items():
                self.logger.error(f"Job {job_id} has missing dependencies: {', '.join(missing_deps)}")
            if not continue_on_error:
                self.logger.error("Missing dependencies detected. Aborting.")
                self.exit_code = 1
                self._print_abort_summary("FAILED", reason="Missing dependencies detected", missing_deps=missing_dependencies)
                return self.exit_code
        # StateManager.start_execution() already handles timing and run summary creation
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{f'STARTING EXECUTION Application {self.application_name} - RUN #{self.run_id}{dry_run_text}{parallel_text}':^90}{Config.COLOR_RESET}")
        print(f"{divider}")
        # Handle resume functionality
        if resume_run_id is not None:
            previous_job_statuses = self.state_manager.setup_resume(resume_run_id, resume_failed_only)
            resume_skip_jobs = self.state_manager.determine_jobs_to_skip()
            # Add resume skip jobs to current skip jobs
            current_skip_jobs = set(skip_jobs or [])
            self.skip_jobs = current_skip_jobs | resume_skip_jobs
            # Mark successful jobs as completed in queue manager
            for job_id in resume_skip_jobs:
                if job_id in previous_job_statuses and previous_job_statuses[job_id] == "SUCCESS":
                    self.completed_jobs.add(job_id)
        # Queue initial jobs that have all dependencies satisfied
        self.queue_manager.queue_initial_jobs()
        def handle_keyboard_interrupt(signal_num, frame):
            self.interrupted = True
            self.logger.info("Received interrupt signal. Stopping after current job...")
            if dry_run:
                print("\nInterrupt received. Stopping dry run cleanly...")
            else:
                print("\nInterrupt received. Will stop after current job completes...")
        import signal
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handle_keyboard_interrupt)
        iteration_count = 0
        try:
            if self.parallel and not dry_run:
                iteration_count = self._run_parallel(max_iter)
            else:
                iteration_count = self._run_sequential(max_iter)
        finally:
            signal.signal(signal.SIGINT, original_handler)
            if self.executor is not None:
                self.logger.debug("Shutting down thread pool executor")
                self.executor.shutdown(wait=True)
                self.executor = None
            self.state_manager.commit_job_statuses()
        if iteration_count >= max_iter:
            self.logger.error(f"Reached maximum iteration limit ({max_iter}). Possible infinite loop detected.")
            self.exit_code = 1
        # Finish execution through state manager
        if not self.dry_run:
            self.state_manager.finish_execution(self.completed_jobs, self.failed_jobs, self.skip_jobs)
            if self._has_valid_email():
                if len(self.failed_jobs) > 0 and self.email_on_failure:
                    self._send_notification(success=False)
                elif len(self.failed_jobs) == 0 and self.email_on_success:
                    self._send_notification(success=True)
            elif self.email_on_failure or self.email_on_success:
                self.logger.warning(f"Email notifications enabled but email_address is invalid: '{self.email_address}'.")
        # Get timing and status info from state manager
        timing_info = self.state_manager.get_timing_info()
        duration_str = timing_info["duration_string"]
        end_date = timing_info["end_time_str"]
        status = self.state_manager.get_run_status()
        status_color = Config.COLOR_DARK_GREEN if self.exit_code == 0 else Config.COLOR_RED
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{'EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {Config.COLOR_YELLOW}{self.run_id}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Status:{Config.COLOR_RESET} {status_color}{status}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_date}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} {duration_str}")
        print(f"{Config.COLOR_CYAN}Jobs Completed:{Config.COLOR_RESET} {Config.COLOR_DARK_GREEN}{len(self.completed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Failed:{Config.COLOR_RESET} {Config.COLOR_RED if len(self.failed_jobs) > 0 else ''}{len(self.failed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Skipped:{Config.COLOR_RESET} {Config.COLOR_YELLOW if len(self.skip_jobs) > 0 else ''}{len(self.skip_jobs)}{Config.COLOR_RESET}")
        # Prepare failed and skipped jobs for summary
        failed_job_order = [j["id"] for j in self.config["jobs"] if j["id"] in self.failed_jobs]
        skipped_due_to_deps = []
        for job_id in self.jobs:
            if job_id not in self.completed_jobs and job_id not in self.failed_jobs and job_id not in self.skip_jobs:
                unmet = [dep for dep in self.dependency_manager.get_job_dependencies(job_id) if dep not in self.completed_jobs and dep not in self.skip_jobs]
                failed_unmet = [dep for dep in unmet if dep in self.failed_jobs]
                skipped_due_to_deps.append((job_id, unmet, failed_unmet))

        # Print summary
        if failed_job_order:
            print("\nFailed Jobs:")
            for job_id in failed_job_order:
                job_log_path = self.job_log_paths.get(job_id, None)
                desc = self.jobs[job_id].get('description', '')
                reason = self.failed_job_reasons.get(job_id, '')
                print(f"  - {job_id}: {desc}\n      Reason: {reason}")
                if job_log_path:
                    print(f"      Log: {job_log_path}")
        if skipped_due_to_deps:
            print("\nSkipped Jobs (unmet dependencies):")
            for job_id, unmet, failed_unmet in skipped_due_to_deps:
                desc = self.jobs[job_id].get('description', '')
                if failed_unmet:
                    print(f"  - {job_id}: {desc}\n      Skipped (failed dependencies: {', '.join(failed_unmet)}; other unmet: {', '.join([d for d in unmet if d not in failed_unmet])})")
                else:
                    print(f"  - {job_id}: {desc}\n      Skipped (unmet dependencies: {', '.join(unmet)})")
        
        # Add resume instructions if run failed
        if self.exit_code != 0 and (failed_job_order or skipped_due_to_deps):
            print(f"\n{Config.COLOR_CYAN}RESUME OPTIONS:{Config.COLOR_RESET}")
            print(f"{Config.COLOR_CYAN}{'='*len('RESUME OPTIONS:')}{Config.COLOR_RESET}")
            
            print(f"To resume this run (all incomplete jobs):")
            print(f"  {Config.COLOR_BLUE}executioner.py -c {self.config_file} --resume-from {self.run_id}{Config.COLOR_RESET}")
            
            if failed_job_order:
                print(f"\nTo retry only failed jobs:")
                print(f"  {Config.COLOR_BLUE}executioner.py -c {self.config_file} --resume-from {self.run_id} --resume-failed-only{Config.COLOR_RESET}")
                
                # Suggest mark-success for manual fixes
                failed_ids = ','.join(failed_job_order)
                print(f"\nIf you manually fixed and ran any failed jobs:")
                print(f"  {Config.COLOR_BLUE}executioner.py --mark-success -r {self.run_id} -j <job_id>{Config.COLOR_RESET}")
                print(f"  Example: executioner.py --mark-success -r {self.run_id} -j {failed_job_order[0]}")
            
            print(f"\nTo see detailed job status:")
            print(f"  {Config.COLOR_BLUE}executioner.py --show-run {self.run_id}{Config.COLOR_RESET}")
        elif self.exit_code == 0:
            # For successful runs, just show how to view details
            print(f"\n{Config.COLOR_CYAN}RUN INFORMATION:{Config.COLOR_RESET}")
            print(f"{Config.COLOR_CYAN}{'='*len('RUN INFORMATION:')}{Config.COLOR_RESET}")
            print(f"To view detailed job status for this run:")
            print(f"  {Config.COLOR_BLUE}executioner.py --show-run {self.run_id}{Config.COLOR_RESET}")
            print(f"\nTo list all recent runs for {self.application_name}:")
            print(f"  {Config.COLOR_BLUE}executioner.py --list-runs {self.application_name}{Config.COLOR_RESET}")
            print(f"\nTo list all recent runs (all applications):")
            print(f"  {Config.COLOR_BLUE}executioner.py --list-runs{Config.COLOR_RESET}")
        
        print(f"{divider}")
        print("\n")
        return self.exit_code

    def _print_abort_summary(self, status, reason=None, missing_deps=None):
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{'EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {self.run_id}")
        print(f"{Config.COLOR_CYAN}Status:{Config.COLOR_RESET} {Config.COLOR_RED}{status}{Config.COLOR_RESET}")
        start_time_str = self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else "N/A"
        end_time_str = self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else "N/A"
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {start_time_str}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_time_str}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} 0:00:00")
        print(f"{Config.COLOR_CYAN}Jobs Completed:{Config.COLOR_RESET} 0")
        print(f"{Config.COLOR_CYAN}Jobs Failed:{Config.COLOR_RESET} 0")
        print(f"{Config.COLOR_CYAN}Jobs Skipped:{Config.COLOR_RESET} 0")
        if reason:
            print(f"\n{Config.COLOR_RED}Execution aborted: {reason}{Config.COLOR_RESET}")
        if missing_deps:
            print(f"\n{Config.COLOR_CYAN}Missing Dependencies:{Config.COLOR_RESET}")
            for job_id, deps in missing_deps.items():
                print(f"  - {Config.COLOR_RED}{job_id}{Config.COLOR_RESET}: {', '.join(deps)}")
        print(f"{divider}")
        print("\n")

    def _run_sequential(self, max_iter: int) -> int:
        iteration_count = 0
        while not self.job_queue.empty() and iteration_count < max_iter and not self.interrupted:
            iteration_count += 1
            try:
                job_id = self.job_queue.get(timeout=1)
            except Empty:
                break
            if job_id in self.skip_jobs or job_id in self.completed_jobs:
                continue
            deps = self.dependency_manager.get_job_dependencies(job_id)
            missing_deps = [dep for dep in deps if dep not in self.completed_jobs and dep not in self.skip_jobs]
            if missing_deps:
                if all(dep in self.jobs for dep in missing_deps):
                    self.logger.warning(f"Job {job_id} queued before dependencies were satisfied: {missing_deps}")
                    continue
                self.logger.warning(f"Job {job_id} has non-existent dependencies: {missing_deps}")
                if self.continue_on_error:
                    self.logger.warning(f"Skipping job {job_id} due to missing dependencies")
                    self.failed_jobs.add(job_id)
                    self.failed_job_reasons[job_id] = f"Missing dependencies: {', '.join(missing_deps)}"
                    continue
                self.logger.error(f"Job {job_id} has missing dependencies. Stopping.")
                self.failed_jobs.add(job_id)
                self.failed_job_reasons[job_id] = f"Missing dependencies: {', '.join(missing_deps)}"
                self.exit_code = 1
                break
            job_success, fail_reason = self._execute_job(job_id)
            if self.interrupted:
                self.logger.info("Execution interrupted, stopping gracefully.")
                break
            with self.lock:
                if job_success:
                    self.queue_manager.add_completed_job(job_id)
                else:
                    self.queue_manager.add_failed_job(job_id, fail_reason or "Unknown failure")
                    if not self.continue_on_error:
                        self.exit_code = 1
                        break
                    self.logger.warning(f"Job {job_id} failed but continuing.")
            if job_success:
                self._queue_dependent_jobs(job_id)
        return iteration_count

    def _run_parallel(self, max_iter: int) -> int:
        iteration_count = 0
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.logger.info(f"Parallel execution with {self.max_workers} workers")
        pending_futures = set()
        while (not self.job_queue.empty() or pending_futures) and iteration_count < max_iter and not self.interrupted:
            iteration_count += 1
            just_completed_jobs = set()
            try:
                completed_futures = list(as_completed(pending_futures, timeout=0.1))
                for future in completed_futures:
                    pending_futures.remove(future)
                    with self.lock:
                        job_id = self.queue_manager.unregister_future(future)
                        if not job_id:
                            continue
                        try:
                            job_success, fail_reason = future.result()
                            if job_success:
                                self.queue_manager.add_completed_job(job_id)
                                just_completed_jobs.add(job_id)
                            else:
                                self.queue_manager.add_failed_job(job_id, fail_reason or "Unknown failure")
                                if not self.continue_on_error:
                                    self.exit_code = 1
                                    self.interrupted = True
                                else:
                                    self.logger.warning(f"Job {job_id} failed but continuing.")
                        except Exception as e:
                            self.logger.error(f"Job {job_id} raised exception: {e}")
                            self.queue_manager.add_failed_job(job_id, f"Exception: {e}")
                            if not self.continue_on_error:
                                self.exit_code = 1
                                self.interrupted = True
                    with self.job_completed_condition:
                        self.job_completed_condition.notify_all()
            except concurrent.futures.TimeoutError:
                pass
            for job_id in just_completed_jobs:
                if not self.interrupted:
                    self._queue_dependent_jobs(job_id)
            jobs_queued = 0
            while not self.job_queue.empty() and not self.interrupted:
                available_worker_slots = self.max_workers - len(pending_futures)
                if available_worker_slots <= 0:
                    break
                try:
                    job_id = self.job_queue.get(timeout=0.1)
                except Empty:
                    break
                should_submit = False
                missing_deps = []
                with self.lock:
                    if (job_id in self.skip_jobs or
                        job_id in self.completed_jobs or
                        job_id in self.active_jobs):
                        continue
                    deps = self.dependency_manager.get_job_dependencies(job_id)
                    missing_deps = [dep for dep in deps if dep not in self.completed_jobs and dep not in self.skip_jobs]
                    if not missing_deps:
                        should_submit = True
                        self.queue_manager.add_active_job(job_id)
                if missing_deps:
                    if all(dep in self.jobs for dep in missing_deps):
                        self.job_queue.put(job_id)
                        break
                    non_existent_deps = [dep for dep in missing_deps if dep not in self.jobs]
                    self.logger.warning(f"Job {job_id} has non-existent dependencies: {non_existent_deps}")
                    if self.continue_on_error:
                        continue
                    self.logger.error(f"Job {job_id} has missing dependencies. Stopping.")
                    self.exit_code = 1
                    self.interrupted = True
                    break
                if should_submit:
                    with self.lock:
                        # Submit the job
                        future = self.executor.submit(self._execute_job, job_id)
                        pending_futures.add(future)
                        self.queue_manager.register_future(future, job_id)
                        self.logger.debug(f"Submitted job {job_id}")
                        jobs_queued += 1
            if not completed_futures and not jobs_queued:
                with self.job_completed_condition:
                    self.job_completed_condition.wait(timeout=1.0)
                if iteration_count % 10 == 0:
                    with self.lock:
                        self.logger.debug(
                            f"Execution status - Queue: {self.job_queue.qsize()}, Active: {len(self.active_jobs)}, "
                            f"Completed: {len(self.completed_jobs)}, Failed: {len(self.failed_jobs)}, Skipped: {len(self.skip_jobs)}"
                        )
        if pending_futures:
            self.logger.info(f"Waiting for {len(pending_futures)} active jobs to complete...")
            futures_to_wait = list(pending_futures)
            max_wait_time = 30
            start_wait = time.time()
            while futures_to_wait and (time.time() - start_wait < max_wait_time):
                try:
                    done, futures_to_wait = concurrent.futures.wait(
                        futures_to_wait, timeout=1.0, return_when=concurrent.futures.FIRST_COMPLETED
                    )
                    for future in done:
                        with self.lock:
                            job_id = self.queue_manager.unregister_future(future)
                            if not job_id:
                                continue
                            pending_futures.discard(future)
                            try:
                                job_success, fail_reason = future.result()
                                if job_success:
                                    self.queue_manager.add_completed_job(job_id)
                                else:
                                    self.queue_manager.add_failed_job(job_id, fail_reason or "Unknown failure")
                            except Exception as e:
                                self.logger.error(f"Exception in job {job_id} during shutdown: {e}")
                                self.queue_manager.add_failed_job(job_id, f"Exception: {e}")
                except Exception as e:
                    self.logger.error(f"Error waiting for jobs during shutdown: {e}")
                    break
            if futures_to_wait:
                self.logger.warning(f"Abandoning {len(futures_to_wait)} jobs after {max_wait_time}s")
                with self.lock:
                    for future in futures_to_wait:
                        future.cancel()
                        job_id = self.queue_manager.unregister_future(future)
                        if job_id:
                            self.queue_manager.add_failed_job(job_id, "Abandoned during shutdown")
                            pending_futures.discard(future)
                            self.logger.warning(f"Job {job_id} abandoned during shutdown")
        return iteration_count

    def _queue_dependent_jobs(self, completed_job_id: str):
        """Queue jobs that depend on the completed job."""
        self.queue_manager.queue_dependent_jobs(completed_job_id, self.dry_run)

    def _send_notification(self, success: bool):
        """Send an email notification using NotificationManager."""
        failed_job_order = [j["id"] for j in self.config["jobs"] if j["id"] in self.failed_jobs]
        skipped_due_to_deps = []
        for job_id in self.jobs:
            if job_id not in self.completed_jobs and job_id not in self.failed_jobs and job_id not in self.skip_jobs:
                unmet = [dep for dep in self.dependency_manager.get_job_dependencies(job_id) if dep not in self.completed_jobs and dep not in self.skip_jobs]
                failed_unmet = [dep for dep in unmet if dep in self.failed_jobs]
                skipped_due_to_deps.append((job_id, unmet, failed_unmet))
        status = "SUCCESS" if success else "FAILED"
        duration = self.end_time - self.start_time if self.end_time and self.start_time else None
        duration_str = str(duration).split('.')[0] if duration else "N/A"
        summary = (
            f"Application: {self.application_name}\n"
            f"Run ID: {self.run_id}\n"
            f"Status: {status}\n"
            f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"End Time: {self.end_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Duration: {duration_str}\n"
            f"Jobs Completed: {len(self.completed_jobs)}\n"
            f"Jobs Failed: {len(self.failed_jobs)}\n"
            f"Jobs Skipped: {len(self.skip_jobs) + len(skipped_due_to_deps)}\n"
        )
        if failed_job_order:
            summary += "\nFailed Jobs:\n"
            for job_id in failed_job_order:
                job_log_path = self.job_log_paths.get(job_id, None)
                desc = self.jobs[job_id].get('description', '')
                reason = self.failed_job_reasons.get(job_id, '')
                summary += f"  - {job_id}: {desc}\n      Reason: {reason}"
                if job_log_path:
                    summary += f"\n      Log: {job_log_path}"
                summary += "\n"
        if skipped_due_to_deps:
            summary += "\nSkipped Jobs (unmet dependencies):\n"
            for job_id, unmet, failed_unmet in skipped_due_to_deps:
                desc = self.jobs[job_id].get('description', '')
                if failed_unmet:
                    summary += f"  - {job_id}: {desc}\n      Skipped (failed dependencies: {', '.join(failed_unmet)}; other unmet: {', '.join([d for d in unmet if d not in failed_unmet])})\n"
                else:
                    summary += f"  - {job_id}: {desc}\n      Skipped (unmet dependencies: {', '.join(unmet)})\n"
        # Collect all log files for this run
        log_pattern = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.job-*.run-{self.run_id}.log")
        attachments = glob.glob(log_pattern)
        # Add main application-level run log (fix for actual filename)
        main_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.run-{self.run_id}.log")
        if not os.path.exists(main_log_path):
            # Fallback to run-None.log if run_id log does not exist
            main_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.run-None.log")
        if os.path.exists(main_log_path):
            attachments.append(main_log_path)
        self.notification_manager.send_notification(
            success=success,
            run_id=self.run_id,
            summary=summary,
            attachments=attachments
        )

    def _has_valid_email(self):
        if isinstance(self.email_address, str):
            return '@' in self.email_address
        elif isinstance(self.email_address, list):
            return any('@' in str(addr) for addr in self.email_address)
        return False

# ... existing code ... 
