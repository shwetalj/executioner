import os
import time
import datetime
import random
import subprocess
from queue import Queue, Empty
from typing import Dict, Any, Tuple
from jobs.checks import CHECK_REGISTRY

class JobRunner:
    def __init__(self, job_id: str, job_config: dict, global_env: dict, main_logger, config: dict, run_id: int, app_name: str, db_connection, validate_timeout, update_job_status, update_retry_history, get_last_exit_code, setup_job_logger):
        self.job_id = job_id
        self.job = job_config
        self.global_env = global_env
        self.main_logger = main_logger  # Main logger for user-facing output
        self.config = config
        self.run_id = run_id
        self.app_name = app_name
        self.db_connection = db_connection
        self.validate_timeout = validate_timeout
        self.update_job_status = update_job_status
        self.update_retry_history = update_retry_history
        self.get_last_exit_code = get_last_exit_code
        self.setup_job_logger = setup_job_logger

    def run(self, dry_run=False):
        command = self.job["command"]
        timeout = self.job.get("timeout", self.config.get("DEFAULT_TIMEOUT", 600))
        max_retries = self.job.get("max_retries", self.config.get("default_max_retries", 0))
        retry_delay = self.job.get("retry_delay", self.config.get("default_retry_delay", 30))
        retry_backoff = self.job.get("retry_backoff", self.config.get("default_retry_backoff", 1.5))
        retry_on_status = self.job.get("retry_on_status", ["ERROR", "FAILED", "TIMEOUT"])
        max_retry_time = self.job.get("max_retry_time", self.config.get("default_max_retry_time", 1800))
        jitter = self.job.get("retry_jitter", self.config.get("default_retry_jitter", 0.1))
        retry_on_exit_codes = self.job.get("retry_on_exit_codes", self.config.get("default_retry_on_exit_codes", [1]))
        current_retry = 0
        retry_history = []
        job_logger, job_file_handler, job_log_path = self.setup_job_logger(self.job_id)
        try:
            # User-facing job start
            self.main_logger.info(f"Starting job '{self.job_id}'")
            self.main_logger.info(f"Running job: {self.job_id} Command: {command}")
            if dry_run:
                print(f"[DRY RUN] Would execute job: {self.job_id} - Command: {command[:60]}{'...' if len(command) > 60 else ''}")
                return True
            # Pre-checks
            pre_checks = self.job.get("pre_checks", [])
            if pre_checks:
                for check in pre_checks:
                    name = check["name"]
                    params = check.get("params", {})
                    func = CHECK_REGISTRY.get(name)
                    args_str = ', '.join(f"{k}={v}" for k, v in params.items())
                    if not func:
                        msg = f"Job {self.job_id} pre_check: {name}({args_str}) - failed (unknown check)"
                        self.main_logger.error(msg)
                        self.update_job_status(self.job_id, "PRECHECK_FAILED")
                        return False
                    try:
                        result = func(**params)
                        status = "passed" if result else "failed"
                        msg = f"Job {self.job_id} pre_check: {name}({args_str}) - {status}"
                        self.main_logger.info(msg)
                        if not result:
                            self.main_logger.error(f"Pre-checks failed for job {self.job_id}. Skipping job execution.")
                            self.update_job_status(self.job_id, "PRECHECK_FAILED")
                            return False
                    except Exception as e:
                        msg = f"Job {self.job_id} pre_check: {name}({args_str}) - failed (error: {e})"
                        self.main_logger.error(msg)
                        self.update_job_status(self.job_id, "PRECHECK_FAILED")
                        return False
            attempt = 1
            start_time = time.time()
            total_retry_time = 0
            while True:
                if total_retry_time > max_retry_time and attempt > 1:
                    self.main_logger.warning(f"Job {self.job_id} exceeded maximum retry time. Giving up after {attempt-1} retries.")
                    return False
                if attempt > 1:
                    retry_msg = f"Retry attempt {attempt}/{max_retries+1} for job {self.job_id}"
                    self.main_logger.info(retry_msg)
                attempt_start = time.time()
                exit_code = None
                try:
                    success = self._run_command(command, timeout, job_logger)
                    duration = round(time.time() - attempt_start, 2)
                    try:
                        exit_code = self.get_last_exit_code(self.job_id)
                    except:
                        pass
                except Exception as e:
                    success = False
                attempt_info = {
                    "attempt": attempt,
                    "timestamp": datetime.datetime.now().isoformat(),
                    "duration": duration if 'duration' in locals() else None,
                    "success": success,
                    "exit_code": exit_code
                }
                retry_history.append(attempt_info)
                if success:
                    # Post-checks
                    post_checks = self.job.get("post_checks", [])
                    post_failed = False
                    if post_checks:
                        for check in post_checks:
                            name = check["name"]
                            params = check.get("params", {})
                            func = CHECK_REGISTRY.get(name)
                            args_str = ', '.join(f"{k}={v}" for k, v in params.items())
                            if not func:
                                msg = f"Job {self.job_id} post_check: {name}({args_str}) - failed (unknown check)"
                                self.main_logger.error(msg)
                                post_failed = True
                                continue
                            try:
                                result = func(**params)
                                status = "passed" if result else "failed"
                                msg = f"Job {self.job_id} post_check: {name}({args_str}) - {status}"
                                self.main_logger.info(msg)
                                if not result:
                                    post_failed = True
                            except Exception as e:
                                msg = f"Job {self.job_id} post_check: {name}({args_str}) - failed (error: {e})"
                                self.main_logger.error(msg)
                                post_failed = True
                    if post_failed:
                        msg = f"Job {self.job_id} failed. Stopping execution."
                        self.main_logger.error(msg)
                        return False
                    # Job completed successfully
                    msg = f"Job '{self.job_id}' completed successfully in {duration:.2f} seconds"
                    self.main_logger.info(msg)
                    self.update_job_status(self.job_id, "SUCCESS")
                    return True
                should_retry = False
                last_status = "FAILED"
                if current_retry < max_retries:
                    should_retry = True
                if last_status in retry_on_status:
                    should_retry = True
                if exit_code is not None and exit_code in retry_on_exit_codes:
                    should_retry = True
                current_retry += 1
                if current_retry > max_retries:
                    self.main_logger.error(f"Job {self.job_id} failed. Stopping execution.")
                    return False
                if not should_retry:
                    return False
                base_delay = retry_delay * (retry_backoff ** (current_retry - 1))
                if jitter > 0:
                    jitter_factor = 1.0 + random.uniform(-jitter, jitter)
                    current_delay = max(0.1, base_delay * jitter_factor)
                else:
                    current_delay = base_delay
                self.main_logger.info(f"Will retry job {self.job_id} in {current_delay:.1f} seconds (attempt {attempt+1}/{max_retries+1})")
                time.sleep(current_delay)
                attempt += 1
                total_retry_time = time.time() - start_time
        finally:
            job_logger.removeHandler(job_file_handler)
            job_file_handler.close()

    def _run_command(self, command, timeout, job_logger):
        # Simplified: just run the command, handle timeout, log output
        env = os.environ.copy()
        env.update({k: str(v) for k, v in self.global_env.items()})
        env.update({k: str(v) for k, v in self.job.get("env_variables", {}).items()})
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
        try:
            for line in process.stdout:
                job_logger.info(line.rstrip())
            exit_code = process.wait(timeout=timeout)
            if exit_code == 0:
                job_logger.info(f"Job {self.job_id}: SUCCESS")
                self.update_job_status(self.job_id, "SUCCESS")
                return True
            else:
                job_logger.error(f"Job {self.job_id}: FAILED with exit code {exit_code}")
                self.update_job_status(self.job_id, "FAILED")
                return False
        except subprocess.TimeoutExpired:
            job_logger.error(f"Job {self.job_id}: TIMEOUT after {timeout} seconds")
            self.update_job_status(self.job_id, "TIMEOUT")
            return False
        except Exception as e:
            job_logger.error(f"Exception during command execution: {e}")
            self.update_job_status(self.job_id, "ERROR")
            return False
        finally:
            if process and process.stdout:
                process.stdout.close()

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