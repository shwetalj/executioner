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
from jobs.logger_factory import setup_logging
from jobs.job_history_manager import JobHistoryManager
from jobs.dependency_manager import DependencyManager
from jobs.notification_manager import NotificationManager

class JobExecutioner:
    def __init__(self, config_file: str):
        # Will be set up properly in _setup_logging
        self.logger = None

        # Set up a basic logger first to handle early errors
        self.logger = logging.getLogger('executioner')
        
        # Clear any existing handlers (prevents duplication)
        for handler in self.logger.handlers[:]:
            
            self.logger.removeHandler(handler)
            
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False  # Don't propagate to root logger
        
        # Load and validate configuration
        try:
            with open(str(config_file), "r") as file:
                self.config = json.load(file)
        except FileNotFoundError:
            self.logger.error(f"Configuration file '{config_file}' not found.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            self.logger.error(f"Configuration file '{config_file}' contains invalid JSON: {e}")
            sys.exit(1)

        # Initialize necessary attributes for logging setup
        self.application_name = self.config.get("application_name",
            os.path.splitext(os.path.basename(config_file))[0])
        self.exit_code = 0
        self.continue_on_error = False
        self.dry_run = False
        self.skip_jobs: Set[str] = set()
        self.start_time = None
        self.end_time = None
        
        # Setup logging (now run_id is available)
        self.logger = setup_logging(self.application_name, None)
        
        # Validate configuration schema
        validate_config(self.config, self.logger)

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
        
        # Handle dependency plugins if specified
        self.dependency_plugins = self.config.get("dependency_plugins", [])
        
        # Job and dependency setup
        self.jobs: Dict[str, Dict] = {job["id"]: job for job in self.config["jobs"]}
        if len(self.jobs) != len(self.config["jobs"]):
            self.logger.error("Duplicate job IDs found in configuration")
            sys.exit(1)
        self.dependency_manager = DependencyManager(self.jobs, self.logger, self.config.get("dependency_plugins", []))
        self.dependencies = self.dependency_manager.dependencies

        # Threading primitives
        self.lock = threading.RLock()
        self.job_completed_condition = threading.Condition()
        self.job_queue: Queue = Queue()
        self.completed_jobs: Set[str] = set()
        self.failed_jobs: Set[str] = set()
        self.failed_job_reasons: Dict[str, str] = {}
        self.queued_jobs: Set[str] = set()
        self.active_jobs: Set[str] = set()
        self.future_to_job_id: Dict[Future, str] = {}
        self.executor = None
        self.interrupted = False

        # Validate dependencies
        if self.dependency_manager.has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            print(f"{Config.COLOR_RED}ERROR: Circular dependencies detected{Config.COLOR_RESET}")
            sys.exit(1)

        missing_deps = self.dependency_manager.check_missing_dependencies()
        if missing_deps:
            for job_id, missing in missing_deps.items():
                self.logger.warning(f"Job {job_id} references dependencies that don't exist: {', '.join(missing)}")
            self.logger.warning("Missing dependencies found. Use --continue-on-error to run anyway.")

        self.job_log_paths = {}  # Track job log file paths

        # Initialize JobHistoryManager (run_id will be set after DB query)
        self.job_history = JobHistoryManager(self.jobs, self.application_name, None, self.logger)
        self.run_id = self.job_history.get_new_run_id()
        self.job_history.run_id = self.run_id

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

    def _get_previous_run_status(self, resume_run_id: int) -> Dict[str, str]:
        job_statuses = {}
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, status FROM job_history WHERE run_id = ?", (resume_run_id,))
                job_statuses = {row[0]: row[1] for row in cursor.fetchall()}
            current_jobs = set(self.jobs.keys())
            previous_jobs = set(job_statuses.keys())
            if current_jobs != previous_jobs:
                if added_jobs := current_jobs - previous_jobs:
                    self.logger.warning(f"New jobs not in previous run: {', '.join(added_jobs)}")
                if removed_jobs := previous_jobs - current_jobs:
                    self.logger.warning(f"Jobs from previous run not in current config: {', '.join(removed_jobs)}")
            return job_statuses
        except sqlite3.Error as e:
            self.logger.error(f"Database error while getting previous run status: {e}")
            return {}

    def _setup_job_logger(self, job_id: str) -> Tuple[logging.Logger, logging.FileHandler, str]:
        job_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.job-{job_id}.run-{self.run_id}.log")
        job_logger = logging.getLogger(f'job_{job_id}')
        job_logger.propagate = False
        for handler in job_logger.handlers[:]:
            job_logger.removeHandler(handler)
        job_file_handler = logging.FileHandler(job_log_path)
        job_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        job_logger.addHandler(job_file_handler)
        job_logger.setLevel(logging.DEBUG)
        job_description = self.jobs[job_id].get('description', '')
        job_command = self.jobs[job_id]['command']
        job_logger.info(f"Executing job - {job_id}: {job_command}")
        self.job_log_paths[job_id] = job_log_path  # Store the job log path
        return job_logger, job_file_handler, job_log_path

    def _validate_command(self, command: str, job_id: str, job_logger: logging.Logger) -> Tuple[bool, str]:
        if not command or not command.strip():
            return True, ""
        security_policy = self.config.get("security_policy", "warn")
        security_level = self.config.get("security_level", "medium")
        command_whitelist = self.config.get("command_whitelist", [])
        if command_whitelist:
            normalized_cmd = command.strip().split()[0] if command.strip() else ""
            if normalized_cmd in command_whitelist:
                job_logger.info(f"Command '{normalized_cmd}' is in the whitelist")
                return True, ""
        workspace_paths = self.config.get("workspace_paths", [])
        try:
            tokens = shlex.split(command)
            if tokens:
                binary_name = tokens[0]
                if workspace_paths and binary_name.startswith('/'):
                    is_allowed_path = any(binary_name.startswith(path) for path in workspace_paths)
                    if not is_allowed_path:
                        reason = f"Command binary path outside of allowed workspace: {binary_name}"
                        job_logger.warning(reason)
                        if security_policy == "block" or security_level == "high":
                            return False, reason
                for arg in tokens[1:]:
                    if '../' in arg or arg.startswith('..'):
                        reason = f"Suspicious path traversal detected in argument: {arg}"
                        job_logger.warning(reason)
                        if security_policy == "block" or security_level == "high":
                            return False, reason
                    sensitive_files = ['/etc/passwd', '/etc/shadow', '/.ssh/', '/id_rsa', '/id_dsa',
                                     '/authorized_keys', '/known_hosts', '/.aws/', '/.config/', '/credentials']
                    for sensitive in sensitive_files:
                        if sensitive in arg:
                            reason = f"Command appears to access sensitive file: {arg}"
                            job_logger.warning(reason)
                            if security_policy == "block" or security_level == "high":
                                return False, reason
        except ValueError as e:
            job_logger.warning(f"Command parsing failed: {e} - treating with caution")
        critical_patterns = [
            (r'`.*`', "Backtick command substitution"),
            (r'\$\(.*\)', "$() command substitution"),
            (r'>\s*/etc/(\w+)', "Writing to /etc files"),
            (r'>\s*/proc/(\w+)', "Writing to /proc"),
            (r'>\s*/sys/(\w+)', "Writing to /sys"),
            (r'[\s < /dev/null | &;]\s*rm\s+-rf\s+/', "Delete root directory"),
            (r'[\s|&;]\s*rm\s+-rf\s+[~.]', "Delete home or current directory"),
            (r'[\s|&;]\s*for\b.*\bdo\b.*\brm\b', "Loop for deletion"),
            (r'\b(sudo|su|doas)\b', "Privilege escalation"),
            (r'>\s*/dev/(sd|hd|xvd|nvme|fd|loop)', "Writing to raw devices"),
            (r'\beval\b.*\$', "Eval with variables is extremely dangerous"),
            (r'[\s|&;]\s*nc\s+.*\s+\-e\s+', "Netcat with program execution"),
            (r'[\s|&;]\s*(shutdown|reboot|halt|poweroff)\b', "System power commands"),
            (r'[\s|&;]\s*dd\s+.*\s+of=/dev/', "Writing to devices with dd"),
            (r'\b(curl|wget)\b.*\|\s*(bash|sh)\b', "Piping web content directly to shell")
        ]
        medium_patterns = [
            (r'[;&\|]\s*rm\s+[-/]', "Dangerous rm commands"),
            (r'[;&\|]\s*rm\s+.*\s+[~/]', "rm targeting home or root"),
            (r'[;&\|]\s*mv\s+[^\s]+\s+/', "Moving to root"),
            (r'[;&\|]\s*find\s+.*\s+(-exec\s+rm|\-delete)', "Find with delete"),
            (r'[;&\|]\s*shred\b', "File secure deletion"),
            (r'[;&\|]\s*chmod\s+([0-7])?777\b', "Overly permissive chmod"),
            (r'[;&\|]\s*chmod\s+\-R\s+.*\s+[~/]', "Recursive chmod from sensitive locations"),
            (r'[;&\|]\s*chown\s+\-R\s+.*\s+[~/]', "Recursive chown"),
            (r'\beval\b', "Eval is dangerous"),
            (r'\bexec\b\s*[^=]', "Exec (when not appearing in assignment)"),
            (r'\bsocat\b.*exec', "Socat with execution"),
            (r'[;&\|]\s*mkfs\b', "Filesystem creation"),
            (r'[;&\|]\s*mount\b', "Mounting filesystems")
        ]
        high_patterns = [
            (r'[;&\|]\s*truncate\s+.*\s+[~/]', "Truncate files in sensitive locations"),
            (r'[;&\|]\s*sed\s+.*\s+-i\s+.*\s+[~/]', "Sed in-place editing of sensitive files"),
            (r'\benv\b.*PATH=', "PATH manipulation"),
            (r'\bwget\b.*\s+-O\s+[~/]', "Overwriting files with wget"),
            (r'\bcurl\b.*\s+-o\s+[~/]', "Overwriting files with curl"),
            (r'\bnohup\b', "Background processes with nohup"),
            (r'\bscp\b.*\s+-r\b', "Recursive SCP"),
            (r'\brsync\b.*\s+--delete\b', "Rsync with delete"),
            (r'\bat\b', "Scheduled tasks"),
            (r'\bcrontab\b', "Cron manipulation"),
            (r'\biptables\b', "Firewall manipulation"),
            (r'\broute\b', "Network routing"),
            (r'\bsystemctl\b', "Service control"),
            (r'\bjournalctl\b', "Log access"),
            (r'\buseradd\b', "User management"),
            (r'\busermod\b', "User modification"),
            (r'\bchpasswd\b', "Password changing")
        ]
        allowlist_patterns = self.config.get("command_allowlist_patterns", [])
        for allow_pattern in allowlist_patterns:
            if re.search(allow_pattern, command, re.IGNORECASE):
                job_logger.info(f"Command matched allowlist pattern: {allow_pattern}")
                return True, ""
        for pattern, description in critical_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Critical security violation: {description}"
                job_logger.error(reason)
                return False, reason
        check_patterns = []
        if security_level in ("medium", "high"):
            check_patterns.extend(medium_patterns)
        if security_level == "high":
            check_patterns.extend(high_patterns)
        for pattern, description in check_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Potentially unsafe operation: {description}"
                job_logger.warning(reason)
                if security_policy == "block":
                    return False, reason
                return True, reason
        return True, ""

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
        process = None
        output_queue = Queue()
        stop_event = threading.Event()
        process_complete = threading.Event()
        try:
            is_safe, reason = self._validate_command(command, job_id, job_logger)
            security_policy = self.config.get("security_policy", "warn")
            if not is_safe:
                error_msg = f"Command execution blocked by security policy: {reason}"
                job_logger.error(error_msg)
                print(f"{Config.COLOR_RED}{error_msg}{Config.COLOR_RESET}")
                self.job_history.update_job_status(job_id, "BLOCKED")
                return False
            if reason:
                warning = f"Command has potentially unsafe patterns but will be executed: {command}"
                job_logger.warning(warning)
                print(f"{Config.COLOR_YELLOW}{warning}{Config.COLOR_RESET}")
            modified_env = os.environ.copy()
            app_env_vars = {k: str(v) for k, v in self.app_env_variables.items()}
            modified_env.update(app_env_vars)
            job = self.jobs[job_id]
            job_env_vars = job.get("env_variables", {})
            job_string_env_vars = {k: str(v) for k, v in job_env_vars.items()}
            modified_env.update(job_string_env_vars)
            env_var_sources = []
            if app_env_vars:
                env_var_sources.append("application")
            if job_env_vars:
                env_var_sources.append(f"job '{job_id}'")
            if env_var_sources:
                all_env_keys = sorted(set(app_env_vars.keys()) | set(job_env_vars.keys()))
                job_logger.info(f"Using environment variables from {' and '.join(env_var_sources)}: {all_env_keys}")
            parsed_command = self._parse_command(command, job_logger)
            if parsed_command and not parsed_command.get('needs_shell', True):
                cmd_args = parsed_command.get('args', [])
                if not cmd_args:
                    job_logger.error("Command parsing failed, no arguments to execute")
                    self.job_history.update_job_status(job_id, "ERROR")
                    return False
                job_logger.info(f"Executing command without shell: {' '.join(cmd_args)}")
                process = subprocess.Popen(
                    cmd_args,
                    shell=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    env=modified_env,
                    preexec_fn=os.setsid if 'posix' in os.name else None
                )
            else:
                if not self.allow_shell:
                    job_logger.error("Shell execution required but disabled by configuration (allow_shell=False)")
                    self.job_history.update_job_status(job_id, "ERROR")
                    return False
                shell_features_needed = parsed_command.get('needs_shell', True) if parsed_command else True
                job_logger.warning(f"Using shell=True for command execution: {command}")
                job_logger.info(f"Shell required because: {parsed_command.get('shell_reason', 'Command requires shell features')}" if parsed_command else "Command parsing failed, defaulting to shell")
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    bufsize=1,
                    env=modified_env,
                    preexec_fn=os.setsid if 'posix' in os.name else None
                )
            job_logger.info(f"Started process with PID: {process.pid}")
            def stream_output():
                try:
                    if process and process.stdout:
                        for line in process.stdout:
                            if stop_event.is_set():
                                break
                            line = line.rstrip()
                            job_logger.info(line)
                            if 'error' in line.lower():
                                output_queue.put((Config.COLOR_RED, f"{line}"))
                            elif 'warning' in line.lower():
                                output_queue.put((Config.COLOR_YELLOW, f"{line}"))
                            else:
                                output_queue.put((Config.COLOR_BLUE, f"{line}"))
                except Exception as e:
                    job_logger.error(f"Error in stream_output: {e}")
                finally:
                    process_complete.set()
            def display_output():
                while not stop_event.is_set() or not output_queue.empty():
                    try:
                        output_queue.get(timeout=1)
                    except Empty:
                        if process_complete.is_set() and output_queue.empty():
                            break
                        continue
                    except Exception as e:
                        job_logger.error(f"Error in display_output: {e}")
                        if stop_event.is_set():
                            break
            output_stream_thread = threading.Thread(target=stream_output, daemon=True)
            output_display_thread = threading.Thread(target=display_output, daemon=True)
            output_stream_thread.start()
            output_display_thread.start()
            try:
                import signal
                exit_code = process.wait(timeout=timeout)
                job_logger.debug(f"Process exited with code {exit_code}")
            except subprocess.TimeoutExpired:
                job_logger.error(f"Job {job_id}: TIMEOUT after {timeout} seconds")
                self._terminate_process(process, job_logger)
                stop_event.set()
                process_complete.set()
                self.job_history.update_job_status(job_id, "TIMEOUT")
                self.logger.error(f"Job '{job_id}' timed out after {timeout} seconds")
                return False
            finally:
                stop_event.set()
                output_stream_thread.join(timeout=5)
                output_display_thread.join(timeout=5)
                if output_stream_thread.is_alive() or output_display_thread.is_alive():
                    job_logger.warning("Output processing threads did not terminate cleanly")
                if process and process.stdout:
                    process.stdout.close()
            if process.returncode == 0:
                job_logger.info(f"Job {job_id}: SUCCESS")
                self.job_history.update_job_status(job_id, "SUCCESS")
                self.logger.info(f"Job '{job_id}' completed successfully")
                return True
            else:
                job_logger.error(f"Job {job_id}: FAILED with exit code {process.returncode}")
                self.job_history.update_job_status(job_id, "FAILED")
                self.logger.error(f"Job '{job_id}' failed with exit code {process.returncode}")
                return False
        except Exception as e:
            error_msg = f"Exception during process execution: {e}"
            job_logger.error(error_msg)
            if process and process.poll() is None:
                self._terminate_process(process, job_logger)
            self.job_history.update_job_status(job_id, "ERROR")
            self.logger.error(f"Job '{job_id}' failed with exception: {e}")
            return False

    def _parse_command(self, command: str, logger: logging.Logger) -> dict:
        if not command or not command.strip():
            return {'args': [], 'needs_shell': False}
        shell_indicators = {
            '|': 'pipe', '&': 'background execution', ';': 'command separator', '<': 'input redirection', '>': 'output redirection', '>>': 'append redirection', '{': 'brace expansion', '}': 'brace expansion', '[': 'glob pattern', ']': 'glob pattern', '$': 'variable expansion', '`': 'command substitution', '\\': 'escape character', '&&': 'conditional execution', '||': 'conditional execution', '2>': 'stderr redirection', '2>&1': 'stderr to stdout redirection', '*': 'wildcard expansion', '?': 'single character wildcard', '~': 'home directory expansion'
        }
        shell_commands = [
            'grep', 'awk', 'sed', 'find', 'xargs', 'for ', 'while ', 'if ', 'case ', 'do ', 'done', 'until ', 'function ', 'alias ', 'source ', './'
        ]
        for indicator, reason in shell_indicators.items():
            if indicator in command:
                return {
                    'needs_shell': True,
                    'shell_reason': f"Command uses shell feature: {reason} ({indicator})",
                    'original_command': command
                }
        for cmd in shell_commands:
            if command.startswith(cmd) or f" {cmd}" in command:
                return {
                    'needs_shell': True,
                    'shell_reason': f"Command uses shell command: {cmd}",
                    'original_command': command
                }
        try:
            args = shlex.split(command)
            if not args:
                logger.warning("Command parsed to empty argument list")
                return {'args': [], 'needs_shell': False}
            cmd_name = args[0]
            if '/' in cmd_name:
                if not os.path.isfile(cmd_name) or not os.access(cmd_name, os.X_OK):
                    if not any(os.path.isfile(os.path.join(path, cmd_name.split('/')[-1])) 
                              for path in os.environ.get('PATH', '').split(os.pathsep) if path):
                        logger.warning(f"Command {cmd_name} not found or not executable")
                        return {
                            'needs_shell': True,
                            'shell_reason': f"Command path not directly executable: {cmd_name}",
                            'original_command': command
                        }
            return {
                'args': args,
                'needs_shell': False,
                'original_command': command
            }
        except ValueError as e:
            logger.warning(f"Command parsing error: {e}")
            return {
                'needs_shell': True,
                'shell_reason': f"Command parsing error: {e}",
                'original_command': command
            }
        except Exception as e:
            logger.warning(f"Unexpected error parsing command: {e}")
            return {
                'needs_shell': True,
                'shell_reason': f"Command parsing error: {e}",
                'original_command': command
            }

    def _terminate_process(self, process: subprocess.Popen, job_logger: logging.Logger):
        try:
            if 'posix' in os.name:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                time.sleep(1)
                if process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
        except OSError as e:
            job_logger.error(f"Error killing process: {e}")

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
            setup_job_logger=self._setup_job_logger
        )
        result, fail_reason = runner.run(dry_run=self.dry_run, continue_on_error=self.continue_on_error, return_reason=True)
        return result, fail_reason

    def _run_dry(self, resume_run_id=None, resume_failed_only=False):
        self.logger.info(f"Starting dry run - printing execution plan")
        if resume_run_id:
            previous_job_statuses = self._get_previous_run_status(resume_run_id)
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
            deps_info = f" {Config.COLOR_CYAN}[DEPS: {', '.join(self.dependencies.get(job_id, [])) or 'none'}]{Config.COLOR_RESET}"
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
            for dep in self.dependencies.get(node, []):
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
        self.continue_on_error = continue_on_error
        self.dry_run = dry_run
        self.skip_jobs = set(skip_jobs or [])
        self.start_time = None
        self.interrupted = False
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
        self.start_time = datetime.datetime.now()
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{f'STARTING EXECUTION Application {self.application_name} - RUN #{self.run_id}{dry_run_text}{parallel_text}':^90}{Config.COLOR_RESET}")
        print(f"{divider}")
        previous_job_statuses = {}
        if resume_run_id is not None:
            previous_job_statuses = self.job_history.get_previous_run_status(resume_run_id)
            if not previous_job_statuses:
                self.logger.error(f"No job history found for run ID {resume_run_id}. Starting fresh.")
            else:
                self.logger.info(f"Resuming from run ID {resume_run_id}" +
                               (" (failed jobs only)" if resume_failed_only else ""))
                for job_id, status in previous_job_statuses.items():
                    if job_id not in self.jobs:
                        continue
                    if status == "SUCCESS":
                        self.skip_jobs.add(job_id)
                        self.completed_jobs.add(job_id)
                        self.logger.info(f"Skipping previously successful job: {job_id}")
                    elif resume_failed_only and status in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.logger.info(f"Will re-run previously failed job: {job_id}")
                    elif not resume_failed_only and status not in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.skip_jobs.add(job_id)
                        self.completed_jobs.add(job_id)
                        self.logger.info(f"Skipping job with status {status}: {job_id}")
        with self.lock:
            for job_id, deps in self.dependencies.items():
                if job_id in self.skip_jobs:
                    continue
                all_deps_satisfied = all(dep in self.completed_jobs or dep in self.skip_jobs for dep in deps)
                if all_deps_satisfied and job_id not in self.queued_jobs:
                    self.job_queue.put(job_id)
                    self.queued_jobs.add(job_id)
                    self.logger.debug(f"Initially queuing job: {job_id}")
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
            self.job_history.commit_job_statuses()
        if iteration_count >= max_iter:
            self.logger.error(f"Reached maximum iteration limit ({max_iter}). Possible infinite loop detected.")
            self.exit_code = 1
        self.end_time = datetime.datetime.now()
        if not self.dry_run:
            status = "SUCCESS" if self.exit_code == 0 else "FAILED"
            duration = self.end_time - self.start_time
            duration_str = str(duration).split('.')[0]
            not_completed = set(self.jobs.keys()) - self.completed_jobs - self.skip_jobs
            if not_completed:
                self.logger.warning(f"The following jobs were not completed: {', '.join(not_completed)}")
                self.exit_code = 1
            if self.email_address and '@' in self.email_address:
                if self.exit_code != 0 and self.email_on_failure:
                    self._send_notification(success=False)
                elif self.exit_code == 0 and self.email_on_success:
                    self._send_notification(success=True)
            elif self.email_on_failure or self.email_on_success:
                self.logger.warning(f"Email notifications enabled but email_address is invalid: '{self.email_address}'.")
        duration = self.end_time - self.start_time
        duration_str = str(duration).split('.')[0]
        end_date = self.end_time.strftime("%Y-%m-%d %H:%M:%S")
        status = "SUCCESS" if self.exit_code == 0 else "FAILED"
        status_color = Config.COLOR_DARK_GREEN if self.exit_code == 0 else Config.COLOR_RED
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{'EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {self.run_id}")
        print(f"{Config.COLOR_CYAN}Status:{Config.COLOR_RESET} {status_color}{status}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_date}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} {duration_str}")
        print(f"{Config.COLOR_CYAN}Jobs Completed:{Config.COLOR_RESET} {Config.COLOR_DARK_GREEN}{len(self.completed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Failed:{Config.COLOR_RESET} {Config.COLOR_RED if len(self.failed_jobs) > 0 else ''}{len(self.failed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Skipped:{Config.COLOR_RESET} {Config.COLOR_YELLOW if len(self.skip_jobs) > 0 else ''}{len(self.skip_jobs)}{Config.COLOR_RESET}")
        if self.failed_jobs:
            print(f"\n{Config.COLOR_CYAN}Failed Jobs (see job log paths below):{Config.COLOR_RESET}")
            for job_id in self.failed_jobs:
                job_log_path = self.job_log_paths.get(job_id, None)
                desc = self.jobs[job_id].get('description', '')
                reason = self.failed_job_reasons.get(job_id, '')
                if job_log_path:
                    print(f"  - {Config.COLOR_RED}{job_id}{Config.COLOR_RESET}: {desc}\n      Reason: {reason}\n      Log: {job_log_path}")
                else:
                    print(f"  - {Config.COLOR_RED}{job_id}{Config.COLOR_RESET}: {desc}\n      Reason: {reason}")
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
            deps = self.dependencies[job_id]
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
                    self.completed_jobs.add(job_id)
                else:
                    self.failed_jobs.add(job_id)
                    self.failed_job_reasons[job_id] = fail_reason or "Unknown failure"
                    self._mark_dependent_jobs_failed(job_id, fail_reason or "Dependency failed")
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
                        job_id = self.future_to_job_id.pop(future, None)
                        if not job_id:
                            continue
                        self.active_jobs.discard(job_id)
                        try:
                            job_success, fail_reason = future.result()
                            if job_success:
                                self.completed_jobs.add(job_id)
                                just_completed_jobs.add(job_id)
                            else:
                                self.failed_jobs.add(job_id)
                                self.failed_job_reasons[job_id] = fail_reason or "Unknown failure"
                                self._mark_dependent_jobs_failed(job_id, fail_reason or "Dependency failed")
                                if not self.continue_on_error:
                                    self.exit_code = 1
                                    self.interrupted = True
                                else:
                                    self.logger.warning(f"Job {job_id} failed but continuing.")
                        except Exception as e:
                            self.logger.error(f"Job {job_id} raised exception: {e}")
                            self.failed_jobs.add(job_id)
                            self._mark_dependent_jobs_failed(job_id, f"Exception: {e}")
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
            available_worker_slots = self.max_workers - len(pending_futures)
            jobs_queued = 0
            while available_worker_slots > 0 and not self.job_queue.empty() and not self.interrupted:
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
                    deps = self.dependencies.get(job_id, set())
                    missing_deps = [dep for dep in deps if dep not in self.completed_jobs and dep not in self.skip_jobs]
                    if not missing_deps:
                        should_submit = True
                        self.active_jobs.add(job_id)
                        self.queued_jobs.discard(job_id)
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
                    future = self.executor.submit(self._execute_job, job_id)
                    with self.lock:
                        pending_futures.add(future)
                        self.future_to_job_id[future] = job_id
                        self.logger.debug(f"Submitted job {job_id}")
                    available_worker_slots -= 1
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
                            job_id = self.future_to_job_id.pop(future, None)
                            if not job_id:
                                continue
                            self.active_jobs.discard(job_id)
                            pending_futures.discard(future)
                            try:
                                job_success, fail_reason = future.result()
                                if job_success:
                                    self.completed_jobs.add(job_id)
                                else:
                                    self.failed_jobs.add(job_id)
                                    self.failed_job_reasons[job_id] = fail_reason or "Unknown failure"
                            except Exception as e:
                                self.logger.error(f"Exception in job {job_id} during shutdown: {e}")
                                self.failed_jobs.add(job_id)
                                self.failed_job_reasons[job_id] = f"Exception: {e}"
                except Exception as e:
                    self.logger.error(f"Error waiting for jobs during shutdown: {e}")
                    break
            if futures_to_wait:
                self.logger.warning(f"Abandoning {len(futures_to_wait)} jobs after {max_wait_time}s")
                with self.lock:
                    for future in futures_to_wait:
                        future.cancel()
                        job_id = self.future_to_job_id.pop(future, None)
                        if job_id:
                            self.active_jobs.discard(job_id)
                            self.failed_jobs.add(job_id)
                            pending_futures.discard(future)
                            self.logger.warning(f"Job {job_id} abandoned during shutdown")
        return iteration_count

    def _mark_dependent_jobs_failed(self, failed_job_id: str, reason: str = None):
        with self.lock:
            visited = set()
            queue = [failed_job_id]
            while queue:
                current_job = queue.pop(0)
                if current_job in visited:
                    continue
                visited.add(current_job)
                for job_id, deps in self.dependencies.items():
                    if current_job in deps and job_id not in visited:
                        if job_id not in self.completed_jobs and job_id not in self.skip_jobs:
                            self.logger.debug(f"Marking job {job_id} as failed due to dependency on {current_job}")
                            self.failed_jobs.add(job_id)
                            self.failed_job_reasons[job_id] = f"Dependency failed: {current_job}" if not reason else reason
                            queue.append(job_id)

    def _queue_dependent_jobs(self, completed_job_id: str):
        if self.dry_run:
            return
        with self.lock:
            self.logger.debug(f"Queueing jobs dependent on {completed_job_id}")
            completed_jobs_snapshot = self.completed_jobs.copy()
            failed_jobs_snapshot = self.failed_jobs.copy()
            skip_jobs_snapshot = self.skip_jobs.copy()
            active_jobs_snapshot = self.active_jobs.copy()
            queued_jobs_snapshot = self.queued_jobs.copy()
            jobs_to_queue = []
            for job_id, deps in self.dependencies.items():
                if completed_job_id not in deps:
                    continue
                if (job_id in completed_jobs_snapshot or
                    job_id in queued_jobs_snapshot or
                    job_id in active_jobs_snapshot or
                    job_id in skip_jobs_snapshot or
                    job_id in failed_jobs_snapshot):
                    continue
                all_deps_satisfied = True
                has_failed_deps = False
                for dep in deps:
                    if dep in failed_jobs_snapshot:
                        has_failed_deps = True
                        self.logger.debug(f"Job {job_id} has failed dependency: {dep}")
                        break
                    if dep not in completed_jobs_snapshot and dep not in skip_jobs_snapshot:
                        all_deps_satisfied = False
                        break
                if has_failed_deps:
                    continue
                if all_deps_satisfied:
                    jobs_to_queue.append(job_id)
                    self.queued_jobs.add(job_id)
            for job_id in jobs_to_queue:
                self.job_queue.put(job_id)
                self.logger.debug(f"Queued dependent job: {job_id}")
            with self.job_completed_condition:
                self.job_completed_condition.notify_all()

    def _update_retry_history(self, job_id: str, retry_history: list, retry_count: int, status: str, reason: str = None) -> None:
        try:
            with db_connection() as conn:
                retry_history_json = json.dumps(retry_history)
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(job_history)")
                columns = [col[1] for col in cursor.fetchall()]
                columns_to_add = []
                if 'retry_history' not in columns:
                    columns_to_add.append(("retry_history", "TEXT"))
                if 'last_exit_code' not in columns:
                    columns_to_add.append(("last_exit_code", "INTEGER"))
                if 'retry_count' not in columns:
                    columns_to_add.append(("retry_count", "INTEGER", "DEFAULT 0"))
                if 'last_error' not in columns:
                    columns_to_add.append(("last_error", "TEXT"))
                if columns_to_add:
                    for col_info in columns_to_add:
                        col_name = col_info[0]
                        col_type = col_info[1]
                        col_constraint = col_info[2] if len(col_info) > 2 else ""
                        alter_sql = f"ALTER TABLE job_history ADD COLUMN {col_name} {col_type} {col_constraint}".strip()
                        try:
                            cursor.execute(alter_sql)
                            self.logger.info(f"Added missing column to job_history: {col_name} {col_type}")
                        except sqlite3.OperationalError as e:
                            if "duplicate column name" not in str(e):
                                raise
                    conn.commit()
                cursor.execute(
                    "SELECT 1 FROM job_history WHERE run_id = ? AND id = ?",
                    (self.run_id, job_id)
                )
                if not cursor.fetchone():
                    job = self.jobs[job_id]
                    cursor.execute(
                        """
                        INSERT INTO job_history
                        (run_id, id, description, command, status, application_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self.run_id,
                            job_id,
                            job.get("description", ""),
                            job["command"],
                            status,
                            self.application_name
                        )
                    )
                    conn.commit()
                try:
                    if reason:
                        cursor.execute(
                            """
                            UPDATE job_history 
                            SET retry_count = ?, retry_history = ?, last_error = ?
                            WHERE run_id = ? AND id = ?
                            """,
                            (retry_count, retry_history_json, reason, self.run_id, job_id)
                        )
                    else:
                        cursor.execute(
                            """
                            UPDATE job_history 
                            SET retry_count = ?, retry_history = ?
                            WHERE run_id = ? AND id = ?
                            """,
                            (retry_count, retry_history_json, self.run_id, job_id)
                        )
                    conn.commit()
                except sqlite3.OperationalError as e:
                    self.logger.warning(f"Could not update retry history, possible schema issue: {e}")
                self.logger.debug(f"Updated retry history for job {job_id}: status={status}, retry_count={retry_count}")
        except sqlite3.Error as e:
            self.logger.warning(f"Failed to update retry history for job {job_id}: {e}")

    def _get_last_exit_code(self, job_id: str) -> int:
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(job_history)")
                columns = [col[1] for col in cursor.fetchall()]
                if 'last_exit_code' not in columns:
                    try:
                        cursor.execute("ALTER TABLE job_history ADD COLUMN last_exit_code INTEGER")
                        conn.commit()
                        self.logger.info("Added missing column to job_history: last_exit_code INTEGER")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e):
                            self.logger.warning(f"Could not add last_exit_code column: {e}")
                    return None
                try:
                    cursor.execute(
                        "SELECT last_exit_code FROM job_history WHERE run_id = ? AND id = ?",
                        (self.run_id, job_id)
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        return int(row[0])
                except sqlite3.OperationalError as e:
                    self.logger.debug(f"Error selecting last_exit_code: {e}")
                return None
        except (sqlite3.Error, ValueError) as e:
            self.logger.debug(f"Could not retrieve exit code for job {job_id}: {e}")
            return None

    def _send_notification(self, success: bool):
        """Send an email notification using NotificationManager."""
        status = "SUCCESS" if success else "FAILED"
        duration = self.end_time - self.start_time if self.end_time and self.start_time else None
        duration_str = str(duration).split('.')[0] if duration else "N/A"
        summary = (
            f"Application: {self.application_name}\n"
            f"Run ID: {self.run_id}\n"
            f"Status: {status}\n"
            f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else 'N/A'}\n"
            f"End Time: {self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else 'N/A'}\n"
            f"Duration: {duration_str}\n"
            f"Jobs Completed: {len(self.completed_jobs)}\n"
            f"Jobs Failed: {len(self.failed_jobs)}\n"
            f"Jobs Skipped: {len(self.skip_jobs)}\n"
        )
        if self.failed_jobs:
            failed_jobs_str = ", ".join(self.failed_jobs)
            summary += f"\nFailed Jobs: {failed_jobs_str}"
        # Collect all log files for this run
        log_pattern = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.job-*.run-{self.run_id}.log")
        attachments = glob.glob(log_pattern)
        self.notification_manager.send_notification(
            success=success,
            run_id=self.run_id,
            summary=summary,
            attachments=attachments
        )

# ... existing code ... 
