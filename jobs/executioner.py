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
from db.sqlite_connection import db_connection
from config.validator import validate_config
from jobs.checks import CHECK_REGISTRY  # Ensure visibility in all contexts
from jobs.job_runner import JobRunner
from jobs.logging_setup import setup_logging, setup_job_logger
from jobs.execution_history_manager import ExecutionHistoryManager
from jobs.dependency_manager import DependencyManager

from jobs.notification_manager import NotificationManager
from jobs.command_utils import validate_command, parse_command
from jobs.env_utils import merge_env_vars, interpolate_env_vars, filter_shell_env
from jobs.queue_manager import QueueManager
from jobs.state_manager import StateManager
from jobs.execution_orchestrator import ExecutionOrchestrator
from jobs.summary_reporter import SummaryReporter

class JobExecutioner:
    def __init__(self, config_file: str, working_dir: str = None):
        # Store the config file path and working directory for later use
        self.config_file = config_file
        self.working_dir = working_dir
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

        # Initialize ExecutionHistoryManager and StateManager
        self.job_history = ExecutionHistoryManager(self.jobs, self.application_name, None, temp_logger)
        self.state_manager = StateManager(self.jobs, self.application_name, self.job_history, temp_logger)

        # Don't initialize run_id yet - will be done in run() method
        self.run_id = None
        self.logger = temp_logger  # Use temp logger for now
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


        # Initialize execution orchestrator for execution coordination
        self.execution_orchestrator = ExecutionOrchestrator(
            jobs=self.jobs,
            queue_manager=self.queue_manager,
            state_manager=self.state_manager,
            dependency_manager=self.dependency_manager,
            logger=self.logger,
            execute_job_func=self._execute_job,
            application_name=self.application_name,
            max_workers=self.max_workers,
            parallel=self.parallel
        )

        # Initialize summary reporter for execution results
        self.summary_reporter = SummaryReporter(self.application_name, config_file)

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
        """Execute a dry run showing the execution plan (delegated to JobScheduler)."""
        return self.execution_orchestrator.run_dry(resume_run_id, resume_failed_only)

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
        
        # Initialize run (with resume_run_id if resuming)
        self.run_id = self.state_manager.initialize_run(resume_run_id)
        
        # Now set up the proper logger with run_id
        self.logger = setup_logging(self.application_name, self.run_id)
        self.job_history.set_logger(self.logger)
        self.state_manager.logger = self.logger
        
        # Handle resume setup if needed
        if resume_run_id is not None:
            previous_job_statuses = self.state_manager.setup_resume(resume_run_id, resume_failed_only)
        
        # Set initial state through state manager
        self.state_manager.start_execution(continue_on_error, dry_run, self.working_dir)
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
        
        # Display appropriate header based on whether this is a resume
        if resume_run_id is not None:
            # This is a resume - show run and attempt
            header_text = f'RESUMING RUN #{self.run_id} (Attempt {self.state_manager.attempt_id}) - {self.application_name}{dry_run_text}{parallel_text}'
            print(f"{Config.COLOR_CYAN}{header_text:^90}{Config.COLOR_RESET}")
        else:
            # This is a new run
            print(f"{Config.COLOR_CYAN}{f'STARTING EXECUTION Application {self.application_name} - RUN #{self.run_id}{dry_run_text}{parallel_text}':^90}{Config.COLOR_RESET}")
        
        print(f"{divider}")
        # Handle resume functionality (already set up above, now just determine skip jobs)
        if resume_run_id is not None:
            resume_skip_jobs = self.state_manager.determine_jobs_to_skip()
            # Add resume skip jobs to current skip jobs
            current_skip_jobs = set(skip_jobs or [])
            self.skip_jobs = current_skip_jobs | resume_skip_jobs
            # Mark successful jobs as completed in queue manager
            for job_id in resume_skip_jobs:
                if job_id in self.state_manager.previous_job_statuses and self.state_manager.previous_job_statuses[job_id] == "SUCCESS":
                    self.completed_jobs.add(job_id)
        # Queue initial jobs that have all dependencies satisfied
        self.queue_manager.queue_initial_jobs()
        # Setup interrupt handler through job scheduler
        original_handler = self.execution_orchestrator.setup_interrupt_handler(dry_run)
        iteration_count = 0
        try:
            if self.parallel and not dry_run:
                iteration_count = self._run_parallel(max_iter)
            else:
                iteration_count = self._run_sequential(max_iter)
        finally:
            # Restore interrupt handler
            self.execution_orchestrator.restore_interrupt_handler(original_handler)
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
        # Generate and display execution summary
        self._display_execution_summary()
        return self.exit_code

    def _display_execution_summary(self) -> None:
        """Display comprehensive execution summary using SummaryReporter."""
        # Get timing and status info from state manager
        timing_info = self.state_manager.get_timing_info()
        duration_str = timing_info["duration_string"]
        end_date = timing_info["end_time_str"]
        status = self.state_manager.get_run_status()
        start_time_str = self.start_time.strftime('%Y-%m-%d %H:%M:%S')

        # Print main summary
        self.summary_reporter.print_execution_summary(
            run_id=self.run_id,
            status=status,
            start_time_str=start_time_str,
            end_time_str=end_date,
            duration_str=duration_str,
            completed_jobs=self.completed_jobs,
            failed_jobs=self.failed_jobs,
            skip_jobs=self.skip_jobs,
            exit_code=self.exit_code,
            attempt_id=self.state_manager.attempt_id
        )

        # Calculate skipped jobs due to dependencies
        skipped_due_to_deps = self.summary_reporter.calculate_skipped_due_to_deps(
            jobs=self.jobs,
            completed_jobs=self.completed_jobs,
            failed_jobs=self.failed_jobs,
            skip_jobs=self.skip_jobs,
            dependency_manager=self.dependency_manager
        )

        # Print detailed job summaries
        self.summary_reporter.print_failed_jobs_summary(
            failed_jobs=self.failed_jobs,
            jobs_config=self.config["jobs"],
            job_log_paths=self.job_log_paths,
            failed_job_reasons=self.failed_job_reasons
        )

        self.summary_reporter.print_skipped_jobs_summary(
            skipped_due_to_deps=skipped_due_to_deps,
            jobs=self.jobs
        )

        # Print resume instructions or run info
        failed_job_order = [j["id"] for j in self.config["jobs"] if j["id"] in self.failed_jobs]
        self.summary_reporter.print_resume_instructions(
            run_id=self.run_id,
            exit_code=self.exit_code,
            failed_job_order=failed_job_order,
            has_skipped_deps=bool(skipped_due_to_deps),
            attempt_id=self.state_manager.attempt_id
        )

        # Print final divider
        self.summary_reporter.print_final_divider()

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
        """Execute jobs sequentially with dependency resolution (delegated to JobScheduler)."""
        return self.execution_orchestrator.run_sequential(max_iter)

    def _run_parallel(self, max_iter: int) -> int:
        """Execute jobs in parallel with dependency resolution (delegated to JobScheduler)."""
        return self.execution_orchestrator.run_parallel(max_iter)

    def _queue_dependent_jobs(self, completed_job_id: str):
        """Queue jobs that depend on the completed job."""
        self.queue_manager.queue_dependent_jobs(completed_job_id, self.dry_run)

    def _send_notification(self, success: bool):
        """Send an email notification using NotificationManager."""
        summary = self.notification_manager.generate_execution_summary(
            success=success,
            run_id=self.run_id,
            start_time=self.start_time,
            end_time=self.end_time,
            completed_jobs=self.completed_jobs,
            failed_jobs=self.failed_jobs,
            skip_jobs=self.skip_jobs,
            jobs_config=self.jobs,
            dependency_manager=self.dependency_manager,
            job_log_paths=self.job_log_paths,
            failed_job_reasons=self.failed_job_reasons
        )
        attachments = self.notification_manager.collect_log_attachments(self.run_id)
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

