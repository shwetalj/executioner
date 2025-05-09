import json
import subprocess
import shlex
import threading
import logging
import sys
import datetime
import os
import re
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

class JobExecutioner:
    def __init__(self, config_file: str):
        # Will be set up properly in _setup_logging
        self.logger = None
        self.job_status_batch = []  # For batching database updates

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
        self.run_id = self._get_new_run_id()
        self.start_time = None
        self.end_time = None
        
        # Setup logging (now run_id is available)
        self._setup_logging()
        
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
        
        # Load dependency plugins now that logger is available
        if self.dependency_plugins:
            self.logger.info(f"Found {len(self.dependency_plugins)} dependency plugins to load")
            self._load_dependency_plugins()

        # Job and dependency setup
        self.jobs: Dict[str, Dict] = {job["id"]: job for job in self.config["jobs"]}
        if len(self.jobs) != len(self.config["jobs"]):
            self.logger.error("Duplicate job IDs found in configuration")
            sys.exit(1)

        self.dependencies: Dict[str, Set[str]] = {
            job["id"]: frozenset(job.get("dependencies", [])) for job in self.config["jobs"]
        }

        # Threading primitives
        self.lock = threading.RLock()
        self.job_completed_condition = threading.Condition()
        self.job_queue: Queue = Queue()
        self.completed_jobs: Set[str] = set()
        self.failed_jobs: Set[str] = set()
        self.queued_jobs: Set[str] = set()
        self.active_jobs: Set[str] = set()
        self.future_to_job_id: Dict[Future, str] = {}
        self.executor = None
        self.interrupted = False

        # Validate dependencies
        has_circular = self._has_circular_dependencies()
        if has_circular:
            self.logger.error("Circular dependencies detected in job configuration")
            sys.exit(1)

        missing_deps = self._check_missing_dependencies()
        if missing_deps:
            for job_id, missing in missing_deps.items():
                self.logger.warning(f"Job {job_id} references dependencies that don't exist: {', '.join(missing)}")
            self.logger.warning("Missing dependencies found. Use --continue-on-error to run anyway.")

        self.job_log_paths = {}  # Track job log file paths

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

    def _load_dependency_plugins(self):
        import importlib.util
        try:
            if not hasattr(self, 'dependency_resolvers'):
                self.dependency_resolvers = {}
            for plugin_path in self.dependency_plugins:
                self.logger.info(f"Loading dependency plugin: {plugin_path}")
                if not os.path.exists(plugin_path):
                    self.logger.error(f"Dependency plugin file not found: {plugin_path}")
                    continue
                try:
                    spec = importlib.util.spec_from_file_location("plugin", plugin_path)
                    if not spec or not spec.loader:
                        self.logger.error(f"Could not load spec for plugin: {plugin_path}")
                        continue
                    plugin = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(plugin)
                    if hasattr(plugin, 'DependencyResolver') and hasattr(plugin.DependencyResolver, '_resolvers'):
                        self.logger.info(f"Successfully loaded dependency plugin with {len(plugin.DependencyResolver._resolvers)} resolvers")
                        self.dependency_resolvers.update(plugin.DependencyResolver._resolvers)
                    else:
                        self.logger.warning(f"Plugin {plugin_path} does not contain expected DependencyResolver class")
                except Exception as e:
                    self.logger.error(f"Error loading dependency plugin {plugin_path}: {e}")
        except Exception as e:
            self.logger.error(f"General error in dependency plugin loading: {e}")

    def _setup_logging(self):
        """Configure logging with rotation and console output."""
        self.master_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.run-{self.run_id}.log")
        master_log_path = self.master_log_path
        app_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.log")
        file_handler = logging.FileHandler(master_log_path)
        app_file_handler = RotatingFileHandler(app_log_path, maxBytes=Config.MAX_LOG_SIZE, backupCount=Config.BACKUP_LOG_COUNT)
        console_handler = logging.StreamHandler(sys.stdout)
        detailed_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        summary_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [RUN #%(run_id)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(detailed_formatter)
        app_file_handler.setFormatter(summary_formatter)

        # Custom formatter for coloring ERROR in red on console and appending log file path
        class ColorFormatter(logging.Formatter):
            RED = '\033[31m'
            RESET = '\033[0m'
            def __init__(self, *args, **kwargs):
                # Remove log_file_path logic
                super().__init__(*args, **kwargs)
            def format(self, record):
                levelname = record.levelname
                if levelname == 'ERROR':
                    record.levelname = f"{self.RED}{levelname}{self.RESET}"
                result = super().format(record)
                record.levelname = levelname  # Restore for other handlers
                return result
        color_formatter = ColorFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(color_formatter)

        old_factory = logging.getLogRecordFactory()
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.run_id = self.run_id
            return record
        logging.setLogRecordFactory(record_factory)
        self.logger = logging.getLogger('executioner')
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        self.logger.addHandler(file_handler)
        self.logger.addHandler(app_file_handler)
        self.logger.addHandler(console_handler)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        #SSJ self.logger.info(f"Logging initialized for {self.application_name} (Run #{self.run_id})")

    def _get_new_run_id(self) -> int:
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(CAST(run_id AS INTEGER)) FROM job_history")
                last_run_id = cursor.fetchone()[0]
                return (last_run_id + 1) if last_run_id is not None else 1
        except (sqlite3.Error, ValueError, TypeError):
            print("Warning: Could not determine last run_id from database, starting with run_id=1")
            return 1

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

    def _update_job_status(self, job_id: str, status: str):
        if self.dry_run:
            return
        job = self.jobs[job_id]
        self.job_status_batch.append((
            self.run_id,
            job_id,
            job.get("description", ""),
            job["command"],
            status,
            self.application_name
        ))

    def _commit_job_statuses(self):
        if not self.job_status_batch:
            return
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO job_history
                    (run_id, id, description, command, status, application_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, self.job_status_batch)
                conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Database batch update error: {e}")
        finally:
            self.job_status_batch.clear()

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
        self.logger.info(f"Starting job '{job_id}'{': ' + job_description if job_description else ''}")
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
                self._update_job_status(job_id, "BLOCKED")
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
                    self._update_job_status(job_id, "ERROR")
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
                    self._update_job_status(job_id, "ERROR")
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
                self._update_job_status(job_id, "TIMEOUT")
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
                self._update_job_status(job_id, "SUCCESS")
                self.logger.info(f"Job '{job_id}' completed successfully")
                return True
            else:
                job_logger.error(f"Job {job_id}: FAILED with exit code {process.returncode}")
                self._update_job_status(job_id, "FAILED")
                self.logger.error(f"Job '{job_id}' failed with exit code {process.returncode}")
                return False
        except Exception as e:
            error_msg = f"Exception during process execution: {e}"
            job_logger.error(error_msg)
            if process and process.poll() is None:
                self._terminate_process(process, job_logger)
            self._update_job_status(job_id, "ERROR")
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

    def _execute_job(self, job_id: str) -> bool:
        job = self.jobs[job_id]
        command = job["command"]
        timeout = job.get("timeout", Config.DEFAULT_TIMEOUT)
        if self.dry_run:
            job_logger = None
            job_file_handler = None
        else:
            job_logger, job_file_handler, _ = self._setup_job_logger(job_id)
            job_logger.info(f"Starting Job: {job_id}")
            job_logger.info(f"Command: {command}")
        # --- Pre-checks integration ---
        pre_checks = job.get("pre_checks", [])
        if not self.dry_run and pre_checks:
            job_logger.info(f"Running pre-checks for job {job_id}: {pre_checks}")
            if not self._run_checks(pre_checks, job_logger, phase="pre", job_id=job_id):
                job_logger.error(f"Pre-checks failed for job {job_id}. Skipping job execution.")
                self._update_job_status(job_id, "PRECHECK_FAILED")
                if job_file_handler:
                    job_logger.removeHandler(job_file_handler)
                    job_file_handler.close()
                return False
        # --- End pre-checks ---
        max_retries = job.get("max_retries", self.config.get("default_max_retries", 0))
        retry_delay = job.get("retry_delay", self.config.get("default_retry_delay", 30))
        retry_backoff = job.get("retry_backoff", self.config.get("default_retry_backoff", 1.5))
        retry_on_status = job.get("retry_on_status", ["ERROR", "FAILED", "TIMEOUT"])
        max_retry_time = job.get("max_retry_time", self.config.get("default_max_retry_time", 1800))
        jitter = job.get("retry_jitter", self.config.get("default_retry_jitter", 0.1))
        retry_on_exit_codes = job.get("retry_on_exit_codes", self.config.get("default_retry_on_exit_codes", [1]))
        current_retry = 0
        retry_history = []
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        "SELECT retry_count, retry_history FROM job_history WHERE run_id = ? AND id = ?", 
                        (self.run_id, job_id)
                    )
                    row = cursor.fetchone()
                    if row:
                        current_retry = row[0] or 0
                        if row[1]:
                            try:
                                retry_history = json.loads(row[1])
                            except (json.JSONDecodeError, TypeError):
                                retry_history = []
                except sqlite3.OperationalError as e:
                    if "no such column" in str(e):
                        self.logger.warning(f"Database schema missing column: {e}")
                    else:
                        raise
        except (sqlite3.Error, Exception) as e:
            if job_logger:
                job_logger.warning(f"Could not retrieve retry information: {e}")
            else:
                self.logger.warning(f"Could not retrieve retry information for job {job_id}: {e}")
            pass
        if self.dry_run:
            print(f"[DRY RUN] Would execute job: {job_id} - Command: {command[:60]}{'...' if len(command) > 60 else ''}")
            retry_info = f" (with {max_retries} retries)" if max_retries > 0 else ""
            self.logger.info(f"[DRY RUN] Would execute job: {job_id}{retry_info}")
            return True
        if max_retries > 0:
            job_logger.info(f"Retry configuration: max_retries={max_retries}, delay={retry_delay}s, backoff={retry_backoff}")
        last_error = None
        attempt = 1
        try:
            if not command.strip():
                job_logger.info(f"Job {job_id}: SUCCESS (empty command)")
                self._update_job_status(job_id, "SUCCESS")
                return True
            timeout = self._validate_timeout(timeout, job_logger)
            start_time = time.time()
            total_retry_time = 0
            if not retry_history:
                retry_history = []
            while True:
                if total_retry_time > max_retry_time and attempt > 1:
                    job_logger.warning(f"Exceeded maximum retry time ({max_retry_time}s). Aborting after {attempt-1} retries.")
                    self.logger.warning(f"Job {job_id} exceeded maximum retry time. Giving up after {attempt-1} retries.")
                    if not self.dry_run:
                        self._update_retry_history(job_id, retry_history, current_retry, 
                                                 "ABANDONED", f"Exceeded max retry time of {max_retry_time}s")
                    return False
                if attempt > 1:
                    retry_msg = f"Retry attempt {attempt}/{max_retries+1} for job {job_id}"
                    job_logger.info(f"{retry_msg} (after {current_delay}s delay)")
                    self.logger.info(retry_msg)
                    print(f"{Config.COLOR_CYAN}{retry_msg}{Config.COLOR_RESET}")
                if jitter > 0 and attempt > 1:
                    jitter_seconds = random.uniform(-jitter, jitter) * current_delay
                    actual_delay = max(0.1, current_delay + jitter_seconds)
                    if abs(jitter_seconds) > 0.1:
                        job_logger.debug(f"Added {jitter_seconds:.2f}s jitter to retry delay")
                attempt_start = time.time()
                attempt_info = {
                    "attempt": attempt,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "start_time": attempt_start
                }
                exit_code = None
                try:
                    success = self._run_subprocess_command(command, job_id, job_logger, timeout)
                    duration = round(time.time() - attempt_start, 2)
                    job_logger.info(f"Job attempt {attempt} duration: {duration} seconds")
                    try:
                        exit_code = self._get_last_exit_code(job_id)
                    except:
                        pass
                except Exception as e:
                    success = False
                    job_logger.error(f"Exception during job execution: {e}")
                attempt_info.update({
                    "duration": duration,
                    "success": success,
                    "exit_code": exit_code
                })
                retry_history.append(attempt_info)
                if not self.dry_run:
                    try:
                        with db_connection() as conn:
                            retry_history_json = json.dumps(retry_history)
                            cursor = conn.cursor()
                            cursor.execute(
                                """
                                UPDATE job_history 
                                SET duration_seconds = ?, retry_count = ?, retry_history = ?, 
                                    last_exit_code = ? 
                                WHERE run_id = ? AND id = ?
                                """,
                                (duration, current_retry, retry_history_json, exit_code, self.run_id, job_id)
                            )
                            conn.commit()
                    except sqlite3.Error as e:
                        job_logger.warning(f"Failed to update job metrics: {e}")
                if success:
                    if attempt > 1:
                        job_logger.info(f"Job {job_id} succeeded after {attempt} attempts")
                        self.logger.info(f"Job {job_id} succeeded after {attempt} attempts")
                    # --- Post-checks integration ---
                    post_checks = job.get("post_checks", [])
                    if post_checks:
                        job_logger.info(f"Running post-checks for job {job_id}: {post_checks}")
                        if not self._run_checks(post_checks, job_logger, phase="post", job_id=job_id):
                            job_logger.error(f"Post-checks failed for job {job_id}. Marking job as failed.")
                            self._update_job_status(job_id, "POSTCHECK_FAILED")
                            return False
                    # --- End post-checks ---
                    return True
                should_retry = False
                retry_reason = None
                last_status = "FAILED"
                if current_retry < max_retries:
                    should_retry = True
                    retry_reason = f"Job failed and current_retry ({current_retry}) < max_retries ({max_retries})"
                if last_status in retry_on_status:
                    should_retry = True
                    retry_reason = f"Status '{last_status}' is in retry_on_status list"
                if exit_code is not None and exit_code in retry_on_exit_codes:
                    should_retry = True
                    retry_reason = f"Exit code {exit_code} is in retry_on_exit_codes list"
                current_retry += 1
                if current_retry > max_retries:
                    job_logger.warning(f"Job {job_id} failed after {attempt} attempts. No more retries (max: {max_retries}).")
                    self.logger.warning(f"Job {job_id} failed after {attempt} attempts. No more retries.")
                    if not self.dry_run:
                        self._update_retry_history(job_id, retry_history, current_retry, 
                                                 "FAILED", f"Reached max retry count ({max_retries})")
                    return False
                if not should_retry:
                    job_logger.info(f"Not retrying job: {retry_reason or f'Status {last_status} not in retry conditions'}")
                    if not self.dry_run:
                        try:
                            with db_connection() as conn:
                                cursor = conn.cursor()
                                cursor.execute(
                                    "UPDATE job_history SET status = ? WHERE run_id = ? AND id = ?",
                                    ("FAILED", self.run_id, job_id)
                                )
                                conn.commit()
                        except sqlite3.Error as e:
                            job_logger.warning(f"Failed to update job status: {e}")
                    return False
                base_delay = retry_delay * (retry_backoff ** (current_retry - 1))
                if jitter > 0:
                    jitter_factor = 1.0 + random.uniform(-jitter, jitter)
                    current_delay = max(0.1, base_delay * jitter_factor)
                else:
                    current_delay = base_delay
                job_logger.info(f"Will retry job {job_id} in {current_delay:.1f} seconds (attempt {attempt+1}/{max_retries+1})")
                if not self.dry_run:
                    self._update_retry_history(job_id, retry_history, current_retry, 
                                             "RETRYING", retry_reason)
                time.sleep(current_delay)
                attempt += 1
                total_retry_time = time.time() - start_time
        except Exception as e:
            job_logger.exception(f"Job {job_id}: ERROR - {e}")
            print(f"{Config.COLOR_RED}Job {job_id}: ERROR - {e}{Config.COLOR_RESET}")
            self._update_job_status(job_id, "ERROR")
            if not self.dry_run:
                try:
                    with db_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE job_history SET last_error = ? WHERE run_id = ? AND id = ?",
                            (str(e), self.run_id, job_id)
                        )
                        conn.commit()
                except sqlite3.Error as db_err:
                    job_logger.warning(f"Failed to store error details: {db_err}")
            return False
        finally:
            job_logger.removeHandler(job_file_handler)
            job_file_handler.close()

    def _get_job_status(self, job_id: str) -> str:
        if self.dry_run:
            return "UNKNOWN"
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT status FROM job_history WHERE run_id = ? AND id = ?",
                    (self.run_id, job_id)
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
                return "UNKNOWN"
        except sqlite3.Error as e:
            self.logger.warning(f"Error retrieving job status: {e}")
            return "UNKNOWN"

    def _validate_timeout(self, timeout: Any, logger: logging.Logger) -> int:
        if timeout is not None:
            try:
                timeout = int(timeout)
                if timeout <= 0:
                    logger.warning(f"Invalid timeout value: {timeout}. Using default of {Config.DEFAULT_TIMEOUT} seconds.")
                    timeout = Config.DEFAULT_TIMEOUT
            except (ValueError, TypeError):
                logger.warning(f"Non-numeric timeout value: {timeout}. Using default of {Config.DEFAULT_TIMEOUT} seconds.")
                timeout = Config.DEFAULT_TIMEOUT
        return timeout

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

    @classmethod
    def generate_test_coverage_report(cls, output_file: str = None, fail_under: float = 70.0, include_branches: bool = True, ci_mode: bool = False):

        """
        Generate a comprehensive test coverage report with detailed metrics per module and function.
        
        This enhanced method provides much more detailed coverage information, including:
        - Line coverage
        - Branch coverage (conditional statements)
        - Function coverage
        - Missing lines and branches
        - Gaps in coverage highlighted
        - Integration with CI systems
        
        Args:
            output_file: Optional path to save the coverage report.
                         If None, prints to stdout.
            fail_under: Coverage percentage below which the process will exit with a non-zero code.
            include_branches: Whether to include branch coverage in the report.
            ci_mode: Whether to generate CI-friendly output (JUnit XML, etc.)
        
        Returns:
            dict: Coverage data containing detailed metrics
            
        Note:
            Requires the `coverage` and `pytest` packages to be installed.
            Install with: pip install coverage pytest pytest-cov
        """
        try:
            import coverage
            import importlib
            import os
            import sys
            import json
            from pathlib import Path
            
            # Get the module path
            module_path = os.path.abspath(__file__)
            module_dir = os.path.dirname(module_path)
            module_name = os.path.basename(module_path).replace(".py", "")
            
            # Find or create a test directory
            test_dir = os.path.join(module_dir, "tests")
            if not os.path.exists(test_dir):
                print(f"No test directory found at {test_dir}. Creating it now.")
                os.makedirs(test_dir)
            
            # Check for test files and recommend test structure if missing
            test_files = [f for f in os.listdir(test_dir) if f.startswith("test_") and f.endswith(".py")]
            if not test_files:
                print(f"No test files found in {test_dir}. You may want to create some.")
                # Create a test template file to help users get started
                template_path = os.path.join(test_dir, f"test_{module_name}.py")
                if not os.path.exists(template_path):
                    with open(template_path, 'w') as f:
                        f.write(f'''import pytest
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from {module_name} import JobExecutioner, Config

# Basic tests to get started
def test_config_initialization():
    """Test that Config initializes with expected default values."""
    assert Config.DEFAULT_TIMEOUT == 600
    assert hasattr(Config, 'LOG_DIR')

def test_job_executioner_initialization():
    """Test basic JobExecutioner initialization with a minimal config."""
    config_json = {{
        "jobs": [
            {{
                "id": "test1",
                "command": "echo 'test'"
            }}
        ]
    }}
    import tempfile
    import json
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        json.dump(config_json, f)
        config_path = f.name
        
    try:
        # This should not raise an exception
        executioner = JobExecutioner(config_path)
        assert isinstance(executioner, JobExecutioner)
        assert "test1" in executioner.jobs
    finally:
        os.unlink(config_path)
''')
                    print(f"Created test template at {template_path}")
            
            # Create .coveragerc configuration file if it doesn't exist
            coverage_config = os.path.join(module_dir, ".coveragerc")
            if not os.path.exists(coverage_config):
                with open(coverage_config, 'w') as f:
                    f.write('''[run]
source = .
omit = 
    */tests/*
    */__pycache__/*
    */site-packages/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
    if __name__ == .__main__.:
    pass
    raise ImportError
    except ImportError

[html]
directory = coverage_html_report
''')
                print(f"Created coverage configuration at {coverage_config}")
            
            # Determine output paths
            if output_file:
                html_dir = os.path.join(output_file, 'html')
                xml_path = os.path.join(output_file, 'coverage.xml')
                json_path = os.path.join(output_file, 'coverage.json')
            else:
                html_dir = os.path.join(module_dir, 'coverage_html_report')
                xml_path = os.path.join(module_dir, 'coverage.xml')
                json_path = os.path.join(module_dir, 'coverage.json')
            
            # Initialize coverage with branch coverage
            cov = coverage.Coverage(
                source=[module_dir],
                omit=["*/tests/*", "*/__pycache__/*", "*/site-packages/*"],
                config_file=coverage_config,
                branch=include_branches,
            )
            
            try:
                # Start coverage tracking
                cov.start()
                
                # Import test modules and run tests with pytest
                # Use pytest-cov for more detailed coverage
                import pytest
                pytest_args = ["-v", test_dir]
                
                if ci_mode:
                    # Add JUnit XML output for CI systems
                    junit_path = os.path.join(module_dir, 'junit.xml')
                    pytest_args.extend(['--junitxml', junit_path])
                
                result = pytest.main(pytest_args)
                
                # Stop coverage tracking
                cov.stop()
                cov.save()
                
                # Create detailed coverage data
                detailed_coverage = {}
                
                # Get coverage data by module and file
                for module_file in cov.get_data().measured_files():
                    module_cov = {}
                    relative_path = os.path.relpath(module_file, module_dir)
                    analysis = cov.analysis2(module_file)
                    
                    module_cov['lines_total'] = len(analysis[1]) + len(analysis[2])
                    module_cov['lines_covered'] = len(analysis[1])
                    module_cov['lines_missed'] = len(analysis[2])
                    module_cov['branches_total'] = len(analysis[3]) + len(analysis[4]) if include_branches else 0
                    module_cov['branches_covered'] = len(analysis[3]) if include_branches else 0
                    module_cov['branches_missed'] = len(analysis[4]) if include_branches else 0
                    
                    if module_cov['lines_total'] > 0:
                        module_cov['line_rate'] = module_cov['lines_covered'] / module_cov['lines_total']
                    else:
                        module_cov['line_rate'] = 0
                        
                    if include_branches and module_cov['branches_total'] > 0:
                        module_cov['branch_rate'] = module_cov['branches_covered'] / module_cov['branches_total']
                    else:
                        module_cov['branch_rate'] = 0
                    
                    module_cov['missing_lines'] = sorted(analysis[2])
                    module_cov['missing_branches'] = sorted(br[0] for br in analysis[4]) if include_branches else []
                    
                    detailed_coverage[relative_path] = module_cov
                
                # Generate reports
                total_cov = cov.report(file=sys.stdout if not output_file else None)
                
                # Generate HTML report with annotated source code
                cov.html_report(directory=html_dir)
                
                # Generate machine-readable reports for CI systems
                cov.xml_report(outfile=xml_path)
                cov.json_report(outfile=json_path)
                
                if output_file:
                    print(f"HTML coverage report saved to: {html_dir}")
                    print(f"XML coverage report saved to: {xml_path}")
                    print(f"JSON coverage report saved to: {json_path}")
                else:
                    print("\nCoverage Report:")
                    print("===============")
                    print(f"Overall coverage: {total_cov:.2f}%")
                
                # Identify coverage gaps and high-risk areas
                high_risk_modules = []
                for module, data in detailed_coverage.items():
                    line_rate = data['line_rate'] * 100
                    if line_rate < fail_under:
                        high_risk_modules.append({
                            'module': module, 
                            'coverage': line_rate,
                            'missing_lines': data['missing_lines'][:10]  # First 10 missing lines
                        })
                
                if high_risk_modules:
                    print("\nHigh Risk Areas (below target coverage):")
                    print("=========================================")
                    for module in sorted(high_risk_modules, key=lambda x: x['coverage']):
                        print(f"{module['module']}: {module['coverage']:.2f}% - Missing lines: {module['missing_lines']}")
                
                # Log coverage statistics for tracking over time
                coverage_data = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "overall_coverage": total_cov,
                    "modules": detailed_coverage,
                    "high_risk_modules": [m['module'] for m in high_risk_modules],
                    "test_result": "PASS" if result == 0 else "FAIL"
                }
                
                # Update coverage history
                coverage_log = os.path.join(module_dir, "coverage_history.json")
                history = []
                if os.path.exists(coverage_log):
                    try:
                        with open(coverage_log, 'r') as f:
                            history = json.load(f)
                    except json.JSONDecodeError:
                        pass  # Start with empty history if file is corrupt
                
                history.append(coverage_data)
                with open(coverage_log, 'w') as f:
                    json.dump(history, f, indent=2)
                
                print(f"Coverage history updated in {coverage_log}")
                print(f"Current coverage: {total_cov:.2f}%")
                
                # Create trend analysis
                if len(history) > 1:
                    prev_coverage = history[-2]["overall_coverage"]
                    coverage_change = total_cov - prev_coverage
                    trend = "↑" if coverage_change > 0 else "↓" if coverage_change < 0 else "="
                    print(f"Coverage trend: {trend} {abs(coverage_change):.2f}% from previous run")
                
                # Generate badge file for README
                badge_path = os.path.join(module_dir, "coverage-badge.svg")
                badge_color = "brightgreen" if total_cov >= 90 else "green" if total_cov >= 80 else "yellowgreen" if total_cov >= 70 else "yellow" if total_cov >= 60 else "orange" if total_cov >= 50 else "red"
                
                badge_content = f"""<svg xmlns="http://www.w3.org/2000/svg" width="106" height="20">
<linearGradient id="a" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
</linearGradient>
<rect rx="3" width="106" height="20" fill="#555"/>
<rect rx="3" x="60" width="46" height="20" fill="#{badge_color}"/>
<path fill="#{badge_color}" d="M60 0h4v20h-4z"/>
<rect rx="3" width="106" height="20" fill="url(#a)"/>
<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="30" y="15" fill="#010101" fill-opacity=".3">coverage</text>
    <text x="30" y="14">coverage</text>
    <text x="82" y="15" fill="#010101" fill-opacity=".3">{total_cov:.0f}%</text>
    <text x="82" y="14">{total_cov:.0f}%</text>
</g>
</svg>"""
                
                with open(badge_path, 'w') as f:
                    f.write(badge_content)
                
                print(f"Coverage badge created at {badge_path}")
                print(f"Add this to your README.md: ![Coverage](./coverage-badge.svg)")
                
                # Exit with error if coverage is below threshold for CI
                if ci_mode and total_cov < fail_under:
                    print(f"Coverage {total_cov:.2f}% is below minimum required {fail_under:.2f}%")
                    return coverage_data, 1  # Return exit code for caller
                
                return coverage_data, 0
                
            finally:
                if not output_file:  # Only erase if we're not saving to file
                    cov.erase()  # Clean up
                
        except ImportError as e:
            print(f"Error: Missing required packages - {e}")
            print("Please install with: pip install coverage pytest pytest-cov")
            return None, 1
        except Exception as e:
            print(f"Error generating coverage report: {e}")
            return None, 1

        pass

    def _send_notification(self, success: bool):
        """Send email notification with retry and TLS support."""
        try:
            hostname = socket.gethostname()
            status = "SUCCESS" if success else "FAILURE"
            subject = f"[{status}] Executioner Job {self.application_name} (Run #{self.run_id})"
            msg = MIMEMultipart()
            msg['From'] = f"Executioner <noreply@{hostname}>"
            msg['To'] = self.email_address
            msg['Subject'] = subject

            duration = None
            if self.start_time and self.end_time:
                duration = self.end_time - self.start_time

            body = f"""
Job Execution Report
===================

Application: {self.application_name}
Run ID: {self.run_id}
Status: {status}
Host: {hostname}
Start Time: {self.start_time}
End Time: {self.end_time}
Duration: {duration}

Completed Jobs: {len(self.completed_jobs)}
Failed Jobs: {len(self.failed_jobs)}
Skipped Jobs: {len(self.skip_jobs)}

"""
            if self.failed_jobs:
                body += "\nFailed Jobs:\n------------\n"
                for job_id in self.failed_jobs:
                    body += f"- {job_id}: {self.jobs[job_id]['description']}\n"

            not_completed = set(self.jobs.keys()) - self.completed_jobs - self.skip_jobs
            if not_completed:
                body += "\nNot Completed Jobs:\n-----------------\n"
                for job_id in not_completed:
                    body += f"- {job_id}: {self.jobs[job_id]['description']}\n"

            msg.attach(MIMEText(body, 'plain'))

            # Send email with retries
            context = ssl.create_default_context()
            for attempt in range(3):
                try:
                    with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=5) as server:
                        server.starttls(context=context)
                        if self.smtp_user and self.smtp_password:
                            server.login(self.smtp_user, self.smtp_password)
                        server.send_message(msg)
                    self.logger.info(f"Sent {status} notification email to {self.email_address}")
                    break
                except (smtplib.SMTPException, ConnectionRefusedError, TimeoutError) as e:
                    self.logger.error(f"Email attempt {attempt+1} failed: {e}")
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        self.logger.info(f"Email that would have been sent:")
                        self.logger.info(f"To: {self.email_address}")
                        self.logger.info(f"Subject: {subject}")
                        self.logger.info(f"Body: {body}")

        except Exception as e:
            self.logger.error(f"Failed to prepare notification email: {e}")


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
        if self._has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            print(f"{Config.COLOR_RED}ERROR: Circular dependencies detected{Config.COLOR_RESET}")
            return 1
        missing_dependencies = self._check_missing_dependencies()
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
        execution_order = self._get_execution_order()
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
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_date}")
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
        self.start_time = datetime.datetime.now()
        self.interrupted = False
        divider = f"{Config.COLOR_CYAN}{'='*90}{Config.COLOR_RESET}"
        dry_run_text = " [DRY RUN]" if dry_run else ""
        parallel_text = f" [PARALLEL: {self.max_workers} workers]" if self.parallel else " [SEQUENTIAL]"
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{f'STARTING EXECUTION Application {self.application_name} - RUN #{self.run_id}{dry_run_text}{parallel_text}':^90}{Config.COLOR_RESET}")
        print(f"{divider}")
        if dry_run:
            try:
                return self._run_dry(resume_run_id, resume_failed_only)
            except KeyboardInterrupt:
                self.logger.info("Dry run interrupted by user")
                print("\nDry run interrupted by user")
                return 0
        if self._has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            self.exit_code = 1
            return self.exit_code
        missing_dependencies = self._check_missing_dependencies()
        if missing_dependencies:
            for job_id, missing_deps in missing_dependencies.items():
                self.logger.error(f"Job {job_id} has missing dependencies: {', '.join(missing_deps)}")
            if not continue_on_error:
                self.logger.error("Missing dependencies detected. Aborting.")
                self.exit_code = 1
                return self.exit_code
        previous_job_statuses = {}
        if resume_run_id is not None:
            previous_job_statuses = self._get_previous_run_status(resume_run_id)
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
            self._commit_job_statuses()
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
            print(f"\n{Config.COLOR_CYAN}Failed Jobs:{Config.COLOR_RESET}")
            for job_id in self.failed_jobs:
                print(f"  - {Config.COLOR_RED}{job_id}{Config.COLOR_RESET}: {self.jobs[job_id].get('description', '')}")
        print(f"{divider}")
        print("\n")
        return self.exit_code

    def _check_missing_dependencies(self):
        result = {}
        for job_id, deps in self.dependencies.items():
            missing = [dep for dep in deps if dep not in self.jobs]
            if missing:
                result[job_id] = missing
        return result

    def _has_circular_dependencies(self):
        def dfs(node, visited, recursion_stack, path=None):
            if path is None:
                path = []
            visited.add(node)
            recursion_stack.add(node)
            path = path + [node]
            for neighbor in self.dependencies.get(node, set()):
                if neighbor not in self.jobs:
                    self.logger.warning(f"Job '{node}' depends on '{neighbor}' which doesn't exist")
                    continue
                if neighbor not in visited:
                    if dfs(neighbor, visited, recursion_stack, path):
                        return True
                elif neighbor in recursion_stack:
                    cycle_path = path + [neighbor]
                    self.logger.error(f"Circular dependency detected: {' -> '.join(cycle_path)}")
                    return True
            recursion_stack.remove(node)
            return False
        visited = set()
        recursion_stack = set()
        for job_id in self.jobs:
            if job_id not in visited:
                if dfs(job_id, visited, recursion_stack):
                    return True
        return False

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
                    continue
                self.logger.error(f"Job {job_id} has missing dependencies. Stopping.")
                self.exit_code = 1
                break
            job_success = self._execute_job(job_id)
            if self.interrupted:
                self.logger.info("Execution interrupted, stopping gracefully.")
                break
            with self.lock:
                if job_success:
                    self.completed_jobs.add(job_id)
                else:
                    self.failed_jobs.add(job_id)
                    self._mark_dependent_jobs_failed(job_id)
                    if not self.continue_on_error:
                        job_log_path = self.job_log_paths.get(job_id, None)
                        extra = f" See log {job_log_path}" if job_log_path else ""
                        self.logger.error(f"Job {job_id} failed. Stopping execution.{extra}")
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
                            job_success = future.result()
                            if job_success:
                                self.completed_jobs.add(job_id)
                                just_completed_jobs.add(job_id)
                            else:
                                self.failed_jobs.add(job_id)
                                self._mark_dependent_jobs_failed(job_id)
                                if not self.continue_on_error:
                                    job_log_path = self.job_log_paths.get(job_id, None)
                                    extra = f" See log {job_log_path}" if job_log_path else ""
                                    self.logger.error(f"Job {job_id} failed. Stopping.{extra}")
                                    self.exit_code = 1
                                    self.interrupted = True
                                else:
                                    self.logger.warning(f"Job {job_id} failed but continuing.")
                        except Exception as e:
                            self.logger.error(f"Job {job_id} raised exception: {e}")
                            self.failed_jobs.add(job_id)
                            self._mark_dependent_jobs_failed(job_id)
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
                                job_success = future.result()
                                if job_success:
                                    self.completed_jobs.add(job_id)
                                else:
                                    self.failed_jobs.add(job_id)
                            except Exception as e:
                                self.logger.error(f"Exception in job {job_id} during shutdown: {e}")
                                self.failed_jobs.add(job_id)
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

    def _mark_dependent_jobs_failed(self, failed_job_id: str):
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

    def _run_checks(self, checks, job_logger, phase="pre", job_id=None):
        from jobs.checks import CHECK_REGISTRY  # Ensure visibility in all contexts
        import datetime
        for check in checks:
            name = check["name"]
            params = check.get("params", {})
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            check_type = f"{phase}_check"
            args_str = ', '.join(f"{k}={v}" for k, v in params.items())
            func = CHECK_REGISTRY.get(name)
            if not func:
                result_str = f"{now} - INFO - Job {job_id} {check_type}: {name}({args_str}) - failed (unknown check)"
                print(result_str)
                job_logger.error(f"Unknown {phase}-check: {name}")
                return False
            try:
                result = func(**params)
                status = "passed" if result else "failed"
                result_str = f"{now} - INFO - Job {job_id} {check_type}: {name}({args_str}) - {status}"
                print(result_str)
                if result:
                    job_logger.info(f"{phase.capitalize()}-check passed: {name}")
                else:
                    job_logger.error(f"{phase.capitalize()}-check failed: {name}")
                    return False
            except Exception as e:
                result_str = f"{now} - INFO - Job {job_id} {check_type}: {name}({args_str}) - failed (error: {e})"
                print(result_str)
                job_logger.error(f"Error running {phase}-check {name}: {e}")
                return False
        return True

# ... existing code ... 
