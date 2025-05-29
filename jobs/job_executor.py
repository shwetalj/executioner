"""
Job Executor for handling individual job execution.

This module provides the JobExecutor class that handles:
- Individual job execution with command validation
- Process management and monitoring  
- Subprocess execution with timeout handling
- Job logging and output streaming
- Retry coordination with JobRunner
"""

import subprocess
import threading
import logging
import os
import signal
import time
from queue import Queue, Empty
from typing import Tuple, Optional, Dict, Any
from logging import FileHandler

from config.loader import Config
from jobs.job_runner import JobRunner
from jobs.command_utils import validate_command, parse_command
from jobs.env_utils import merge_env_vars, interpolate_env_vars


class JobExecutor:
    """
    Handles execution of individual jobs with process management and monitoring.
    
    This class encapsulates all job execution logic including command validation,
    process spawning, output streaming, and timeout handling.
    """
    
    def __init__(
        self, 
        config: Dict[str, Any],
        app_env_variables: Dict[str, str],
        cli_env_variables: Dict[str, str],
        shell_env: Dict[str, str],
        application_name: str,
        run_id: int,
        main_logger: logging.Logger,
        job_history_manager: Any,  # JobHistoryManager type
        setup_job_logger_func: Any  # Function type
    ):
        """
        Initialize the JobExecutor.
        
        Args:
            config: Global configuration dictionary
            app_env_variables: Application-level environment variables
            cli_env_variables: CLI-provided environment variables  
            shell_env: Filtered shell environment variables
            application_name: Name of the application
            run_id: Current run ID
            main_logger: Main logger instance
            job_history_manager: Job history manager for status updates
            setup_job_logger_func: Function to setup job-specific loggers
        """
        self.config = config
        self.app_env_variables = app_env_variables
        self.cli_env_variables = cli_env_variables
        self.shell_env = shell_env
        self.application_name = application_name
        self.run_id = run_id
        self.logger = main_logger
        self.job_history = job_history_manager
        self.setup_job_logger = setup_job_logger_func
        
        # Job execution tracking
        self.job_log_paths: Dict[str, str] = {}
    
    def execute_job(self, job_id: str, job_config: Dict[str, Any], dry_run: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Execute a single job.
        
        Args:
            job_id: ID of the job to execute
            job_config: Job configuration dictionary
            dry_run: Whether this is a dry run
            
        Returns:
            Tuple of (success, failure_reason)
        """
        if dry_run:
            self.logger.info(f"DRY RUN: Would execute job {job_id}")
            return True, None
        
        # Use JobRunner for execution with retry logic
        runner = JobRunner(
            job_id=job_id,
            job_config=job_config,
            global_env=self.app_env_variables,
            main_logger=self.logger,
            config=self.config,
            run_id=self.run_id,
            app_name=self.application_name,
            db_connection=None,  # Will be set by caller
            validate_timeout=self._validate_timeout,
            update_job_status=self.job_history.update_job_status,
            update_retry_history=self.job_history.update_retry_history,
            get_last_exit_code=self.job_history.get_last_exit_code,
            setup_job_logger=self.setup_job_logger,
            cli_env=self.cli_env_variables,
            shell_env=self.shell_env
        )
        
        # Set job history reference
        runner.job_history = self.job_history
        
        # Execute with retry logic
        result, fail_reason = runner.run(
            dry_run=dry_run, 
            continue_on_error=True,  # Let caller decide what to do with failures
            return_reason=True
        )
        
        return result, fail_reason
    
    def run_subprocess_command(
        self, 
        command: str, 
        job_id: str, 
        job_logger: logging.Logger, 
        timeout: int
    ) -> bool:
        """
        Execute a subprocess command with comprehensive monitoring.
        
        Args:
            command: Command to execute
            job_id: ID of the job being executed
            job_logger: Logger for this specific job
            timeout: Timeout in seconds
            
        Returns:
            True if command succeeded, False otherwise
        """
        process = None
        output_queue = Queue()
        stop_event = threading.Event()
        process_complete = threading.Event()
        
        try:
            # Validate command security
            is_safe, reason = validate_command(command, job_id, job_logger, self.config)
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
            
            # Setup environment variables
            job_config = {"env_variables": {}}  # Will be provided by caller
            merged_env = merge_env_vars(self.app_env_variables, job_config.get("env_variables", {}))
            merged_env = merge_env_vars(merged_env, self.cli_env_variables)
            merged_env = interpolate_env_vars(merged_env, job_logger)
            
            # Start with filtered shell environment
            modified_env = self.shell_env.copy()
            modified_env.update(merged_env)
            
            # Log environment variable sources
            env_var_sources = []
            if self.app_env_variables:
                env_var_sources.append("application")
            if job_config.get("env_variables"):
                env_var_sources.append(f"job '{job_id}'")
            if env_var_sources:
                all_env_keys = sorted(set(self.app_env_variables.keys()) | set(job_config.get("env_variables", {}).keys()))
                job_logger.info(f"Using environment variables from {' and '.join(env_var_sources)}: {all_env_keys}")
            
            # Parse and execute command
            parsed_command = parse_command(command, job_logger)
            
            if parsed_command and not parsed_command.get('needs_shell', True):
                # Execute without shell
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
                # Execute with shell
                allow_shell = self.config.get("allow_shell", True)
                if not allow_shell:
                    job_logger.error("Shell execution required but disabled by configuration (allow_shell=False)")
                    self.job_history.update_job_status(job_id, "ERROR")
                    return False
                
                shell_reason = parsed_command.get('shell_reason', 'Command requires shell features') if parsed_command else 'Command parsing failed, defaulting to shell'
                job_logger.warning(f"Using shell=True for command execution: {command}")
                job_logger.info(f"Shell required because: {shell_reason}")
                
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
            
            # Stream output in separate thread
            def stream_output():
                try:
                    if process and process.stdout:
                        for line in process.stdout:
                            if stop_event.is_set():
                                break
                            line = line.rstrip()
                            job_logger.info(line)
                            
                            # Colorize output based on content
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
            
            # Display output in separate thread  
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
            
            # Start output handling threads
            output_stream_thread = threading.Thread(target=stream_output, daemon=True)
            output_display_thread = threading.Thread(target=display_output, daemon=True)
            output_stream_thread.start()
            output_display_thread.start()
            
            try:
                # Wait for process completion with timeout
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
                # Clean up output threads
                stop_event.set()
                output_stream_thread.join(timeout=5)
                output_display_thread.join(timeout=5)
                
                if output_stream_thread.is_alive() or output_display_thread.is_alive():
                    job_logger.warning("Output processing threads did not terminate cleanly")
                
                if process and process.stdout:
                    process.stdout.close()
            
            # Check final result
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
    
    def _terminate_process(self, process: subprocess.Popen, job_logger: logging.Logger) -> None:
        """
        Terminate a running process gracefully.
        
        Args:
            process: Process to terminate
            job_logger: Logger for the job
        """
        try:
            if 'posix' in os.name:
                # POSIX systems: terminate process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                time.sleep(1)
                if process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                # Windows systems: terminate process directly
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
        except OSError as e:
            job_logger.error(f"Error killing process: {e}")
    
    def _validate_timeout(self, timeout: Optional[int], logger: Optional[logging.Logger] = None) -> Optional[int]:
        """
        Validate and normalize timeout value.
        
        Args:
            timeout: Timeout value to validate
            logger: Optional logger for warnings
            
        Returns:
            Validated timeout value
        """
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
    
    def get_job_log_path(self, job_id: str) -> Optional[str]:
        """
        Get the log file path for a specific job.
        
        Args:
            job_id: ID of the job
            
        Returns:
            Log file path if available, None otherwise
        """
        return self.job_log_paths.get(job_id)