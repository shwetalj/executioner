import os
import time
import datetime
import random
import subprocess
from queue import Queue, Empty
from typing import Dict, Any, Tuple
from jobs.checks import CHECK_REGISTRY
from jobs.check_runner import run_checks
from jobs.job_status_mixin import JobStatusMixin
from jobs.env_utils import merge_env_vars, interpolate_env_vars

# Exit code constants
EXIT_CODE_SUCCESS = 0
EXIT_CODE_TIMEOUT = -1  # Process timed out and was killed
EXIT_CODE_EXCEPTION = -2  # Exception occurred during execution

class JobRunner(JobStatusMixin):
    def __init__(self, job_id: str, job_config: dict, global_env: dict, main_logger, config: dict, run_id: int, app_name: str, db_connection, update_job_status, update_retry_history, get_last_exit_code, setup_job_logger, cli_env=None, shell_env=None):
        self.job_id = job_id
        self.job = job_config
        self.global_env = global_env
        self.cli_env = cli_env or {}
        self.shell_env = shell_env if shell_env is not None else dict(os.environ)  # Default to full environ for backward compatibility
        self.main_logger = main_logger  # Main logger for user-facing output
        self.config = config
        self.run_id = run_id
        self.app_name = app_name
        self.db_connection = db_connection
        self.job_history = None  # Will be set externally
        self.logger = main_logger  # Use main_logger for mixin
        self.get_last_exit_code = get_last_exit_code
        self.setup_job_logger = setup_job_logger

    def run(self, dry_run=False, continue_on_error=False, return_reason=False):
        command = self.job["command"]
        # Determine timeout: job['timeout'] > config['default_timeout'] > 10800
        timeout = self.job.get("timeout")
        timeout_source = None
        if timeout is not None:
            timeout_source = f"timeout={timeout}"
        else:
            timeout = self.config.get("default_timeout")
            if timeout is not None:
                timeout_source = f"default timeout={timeout}"
        if timeout is None:
            timeout = 10800
            timeout_source = "default timeout=10800"
        else:
            try:
                timeout = int(timeout)
            except Exception:
                timeout = 10800
                timeout_source = "default timeout=10800"
        max_retries = self.job.get("max_retries", self.config.get("default_max_retries", 0))
        retry_delay = self.job.get("retry_delay", self.config.get("default_retry_delay", 30))
        retry_backoff = self.job.get("retry_backoff", self.config.get("default_retry_backoff", 1.5))
        retry_on_status = self.job.get("retry_on_status", ["ERROR", "FAILED", "TIMEOUT"])
        max_retry_time = self.job.get("max_retry_time", self.config.get("default_max_retry_time", 1800))
        jitter = self.job.get("retry_jitter", self.config.get("default_retry_jitter", 0.1))
        retry_on_exit_codes = self.job.get("retry_on_exit_codes", self.config.get("default_retry_on_exit_codes", [1]))
        retry_history = []
        job_logger, job_file_handler, job_log_path = self.setup_job_logger(self.job_id)
        fail_reason = None
        try:
            # User-facing job start
            self.main_logger.info(f"Starting job '{self.job_id}'")
            self.main_logger.info(f"Running job: {self.job_id} Command: {command}")
            if dry_run:
                print(f"[DRY RUN] Would execute job: {self.job_id} - Command: {command[:60]}{'...' if len(command) > 60 else ''}")
                if return_reason:
                    return True, None
                return True
            if not command.strip():
                self.main_logger.info(f"Job {self.job_id}: SUCCESS (empty command)")
                self.mark_success(self.job_id)
                if return_reason:
                    return True, None
                return True
            # Pre-checks
            pre_checks = self.job.get("pre_checks", [])
            if pre_checks:
                pre_check_start = datetime.datetime.now()
                if not run_checks(pre_checks, job_logger, phase="pre", job_id=self.job_id):
                    self.main_logger.error(f"Pre-checks failed for job {self.job_id}. Skipping job execution.")
                    pre_check_duration = (datetime.datetime.now() - pre_check_start).total_seconds()
                    self.mark_failed(self.job_id, "PRECHECK_FAILED", duration=pre_check_duration, start_time=pre_check_start.strftime('%Y-%m-%d %H:%M:%S'))
                    fail_reason = f"Pre-check failed"
                    if return_reason:
                        return False, fail_reason
                    return False
            attempt = 0
            start_time = time.time()
            total_retry_time = 0

            while attempt <= max_retries:
                # Check total retry time limit (skip on first attempt)
                if attempt > 0 and total_retry_time > max_retry_time:
                    self.main_logger.warning(f"Job {self.job_id} exceeded maximum retry time of {max_retry_time}s after {attempt} attempts.")
                    fail_reason = f"Exceeded max retry time after {attempt} attempts"
                    if return_reason:
                        return False, fail_reason
                    return False

                # Log retry attempt
                if attempt > 0:
                    retry_msg = f"Retry attempt {attempt}/{max_retries} for job {self.job_id}"
                    self.main_logger.info(retry_msg)

                # Execute the job
                attempt_start = time.time()
                attempt_start_dt = datetime.datetime.now()
                exit_code = None
                try:
                    status = self._run_command(command, timeout, job_logger, attempt_start_dt)
                    exit_code = getattr(self, 'last_exit_code', None)
                except Exception as e:
                    status = "ERROR"
                    job_logger.error(f"Exception during job execution: {e}")
                    fail_reason = f"Exception during execution: {e}"

                duration = round(time.time() - attempt_start, 2)

                # Record attempt info
                attempt_info = {
                    "attempt": attempt + 1,  # Human-readable attempt number
                    "timestamp": datetime.datetime.now().isoformat(),
                    "duration": duration,
                    "success": status == "SUCCESS",
                    "exit_code": exit_code,
                    "status": status
                }
                retry_history.append(attempt_info)

                # Handle successful execution
                if status == "SUCCESS":
                    # Post-checks
                    post_checks = self.job.get("post_checks", [])
                    if post_checks:
                        if not run_checks(post_checks, job_logger, phase="post", job_id=self.job_id):
                            msg = f"Job {self.job_id} failed post-checks after {duration:.2f} seconds."
                            self.main_logger.error(msg)
                            fail_reason = "Post-check failed"
                            status = "POSTCHECK_FAILED"
                            # Don't return here - let retry logic handle it
                        else:
                            msg = f"Job '{self.job_id}' completed successfully in {duration:.2f} seconds"
                            self.main_logger.info(msg)
                            self.mark_success(self.job_id, duration=duration, start_time=attempt_start_dt.strftime('%Y-%m-%d %H:%M:%S'))
                            if return_reason:
                                return True, None
                            return True
                    else:
                        msg = f"Job '{self.job_id}' completed successfully in {duration:.2f} seconds"
                        self.main_logger.info(msg)
                        self.mark_success(self.job_id, duration=duration, start_time=attempt_start_dt.strftime('%Y-%m-%d %H:%M:%S'))
                        if return_reason:
                            return True, None
                        return True

                # Job failed - determine if we should retry
                if attempt < max_retries:
                    should_retry = False

                    # Check if status allows retry
                    if status in retry_on_status:
                        should_retry = True
                        self.main_logger.debug(f"Job {self.job_id} status '{status}' is in retry_on_status list")

                    # Check if exit code allows retry
                    if exit_code is not None and exit_code in retry_on_exit_codes:
                        should_retry = True
                        self.main_logger.debug(f"Job {self.job_id} exit code {exit_code} is in retry_on_exit_codes list")

                    if should_retry:
                        # Calculate retry delay
                        base_delay = retry_delay * (retry_backoff ** attempt)
                        if jitter > 0:
                            jitter_factor = 1.0 + random.uniform(-jitter, jitter)
                            current_delay = max(0.1, base_delay * jitter_factor)
                        else:
                            current_delay = base_delay

                        self.main_logger.info(f"Will retry job {self.job_id} in {current_delay:.1f} seconds (attempt {attempt+1}/{max_retries})")
                        time.sleep(current_delay)
                        attempt += 1
                        total_retry_time = time.time() - start_time
                        continue
                    else:
                        # No retry conditions met
                        self.main_logger.error(f"Job {self.job_id} failed with status '{status}' and exit code {exit_code}. No retry conditions met.")
                        if not fail_reason:
                            fail_reason = f"Job failed with status '{status}' (exit code: {exit_code})"
                        break
                else:
                    # Max retries reached
                    self.main_logger.error(f"Job {self.job_id} failed after {attempt + 1} attempts.")
                    if not fail_reason:
                        fail_reason = f"Job failed after {attempt + 1} attempts (status: {status}, exit code: {exit_code})"
                    break

            # Job failed - update status and return
            if not continue_on_error:
                self.main_logger.error("Stopping execution.")
            if return_reason:
                return False, fail_reason
            return False
        finally:
            try:
                job_logger.removeHandler(job_file_handler)
            except Exception as e:
                # Log the error but continue to try closing the handler
                if hasattr(self, 'main_logger'):
                    self.main_logger.debug(f"Error removing handler: {e}")
            try:
                job_file_handler.close()
            except Exception as e:
                # Log the error but continue
                if hasattr(self, 'main_logger'):
                    self.main_logger.debug(f"Error closing file handler: {e}")

    def _run_command(self, command, timeout, job_logger, start_time_dt=None):
        import threading
        # Merge environment variables: app -> job -> CLI (CLI has highest precedence)
        merged_env = merge_env_vars(self.global_env, self.job.get("env_variables", {}))
        merged_env = merge_env_vars(merged_env, self.cli_env)
        # Interpolate variables after merging so job vars can reference app/CLI vars
        merged_env = interpolate_env_vars(merged_env, job_logger)
        # Start with filtered shell environment instead of full os.environ
        env = self.shell_env.copy()
        env.update(merged_env)
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
            env=env,
            preexec_fn=os.setsid if 'posix' in os.name else None
        )
        self.last_exit_code = None  # Track exit code
        stop_reading = threading.Event()
        def read_output():
            try:
                for line in process.stdout:
                    if stop_reading.is_set():
                        break
                    job_logger.info(line.rstrip())
            except Exception as e:
                job_logger.error(f"Error reading process output: {e}")
        reader_thread = threading.Thread(target=read_output, daemon=True)
        reader_thread.start()
        try:
            try:
                exit_code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timeout_val = getattr(self, 'timeout', timeout)
                timeout_source = getattr(self, 'timeout_source', f"timeout={timeout}")
                msg = f"Job {self.job_id} timed out after {timeout} seconds ({timeout_source})."
                job_logger.error(msg)
                self.main_logger.error(msg)
                try:
                    if 'posix' in os.name:
                        import signal
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        time.sleep(1)
                        if process.poll() is None:
                            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        process.terminate()
                        time.sleep(1)
                        if process.poll() is None:
                            process.kill()
                except Exception as e:
                    job_logger.error(f"Error terminating process on timeout: {e}")
                stop_reading.set()
                reader_thread.join(timeout=5)
                if reader_thread.is_alive():
                    job_logger.warning("Output reading thread did not terminate cleanly after timeout")
                # Set exit code to EXIT_CODE_TIMEOUT for timeout
                self.last_exit_code = EXIT_CODE_TIMEOUT
                # Calculate duration from start if available
                if start_time_dt:
                    duration = (datetime.datetime.now() - start_time_dt).total_seconds()
                    self.mark_failed(self.job_id, "TIMEOUT", duration=duration, start_time=start_time_dt.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    self.mark_failed(self.job_id, "TIMEOUT")
                return "TIMEOUT"
            stop_reading.set()
            reader_thread.join(timeout=5)
            if reader_thread.is_alive():
                job_logger.warning("Output reading thread did not terminate cleanly after process exit")
            self.last_exit_code = exit_code
            if exit_code == EXIT_CODE_SUCCESS:
                job_logger.info(f"Job {self.job_id}: SUCCESS")
                # Calculate duration from start if available
                if start_time_dt:
                    duration = (datetime.datetime.now() - start_time_dt).total_seconds()
                    self.mark_success(self.job_id, duration=duration, start_time=start_time_dt.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    self.mark_success(self.job_id)
                return "SUCCESS"
            else:
                job_logger.error(f"Job {self.job_id}: FAILED with exit code {exit_code}")
                # Calculate duration from start if available
                if start_time_dt:
                    duration = (datetime.datetime.now() - start_time_dt).total_seconds()
                    self.mark_failed(self.job_id, "FAILED", duration=duration, start_time=start_time_dt.strftime('%Y-%m-%d %H:%M:%S'))
                else:
                    self.mark_failed(self.job_id, "FAILED")
                return "FAILED"
        except Exception as e:
            job_logger.error(f"Exception during command execution: {e}")
            # Set exit code to EXIT_CODE_EXCEPTION for exceptions
            self.last_exit_code = EXIT_CODE_EXCEPTION
            # Calculate duration from start if available
            if start_time_dt:
                duration = (datetime.datetime.now() - start_time_dt).total_seconds()
                self.mark_failed(self.job_id, "ERROR", duration=duration, start_time=start_time_dt.strftime('%Y-%m-%d %H:%M:%S'))
            else:
                self.mark_failed(self.job_id, "ERROR")
            return "ERROR"
        finally:
            # Ensure thread cleanup
            stop_reading.set()
            if reader_thread.is_alive():
                reader_thread.join(timeout=1)
            if process and process.stdout:
                try:
                    process.stdout.close()
                except Exception:
                    pass  # Best effort

    def _run_checks(self, checks, job_logger, phase="pre"):
        for check in checks:
            name = check["name"]
            params = check.get("params", {})
            func = CHECK_REGISTRY.get(name)
            if not func:
                job_logger.error(f"Unknown {phase}-check: {name}")
                return False
            try:
                result = func(**params)
                if not result:
                    job_logger.error(f"{phase.capitalize()}-check failed: {name}")
                    return False
            except Exception as e:
                job_logger.error(f"Error running {phase}-check {name}: {e}")
                return False
        return True

