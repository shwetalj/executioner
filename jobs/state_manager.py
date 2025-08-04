"""
State Manager for handling execution state and persistence.

This module provides the StateManager class that handles:
- Execution run state (run_id, timing, exit codes)
- Resume functionality and previous run analysis
- Run summary creation and updates
- Job status persistence coordination
- State validation and consistency checks
"""

import datetime
import logging
from typing import Dict, Optional, Any, Set
from jobs.execution_history_manager import ExecutionHistoryManager


class StateManager:
    """
    Manages execution state, run lifecycle, and persistence operations.

    This class encapsulates all state-related operations including run tracking,
    resume functionality, and coordination with the job history persistence layer.
    """

    def __init__(
        self,
        jobs: Dict[str, Dict],
        application_name: str,
        job_history: ExecutionHistoryManager,
        logger: logging.Logger
    ):
        """
        Initialize the StateManager.

        Args:
            jobs: Dictionary of job configurations
            application_name: Name of the application
            job_history: ExecutionHistoryManager for persistence operations
            logger: Logger instance for debug/info messages
        """
        self.jobs = jobs
        self.application_name = application_name
        self.job_history = job_history
        self.logger = logger

        # Run state
        self.run_id: Optional[int] = None
        self.start_time: Optional[datetime.datetime] = None
        self.end_time: Optional[datetime.datetime] = None
        self.exit_code: int = 0

        # Execution control flags
        self.continue_on_error: bool = False
        self.dry_run: bool = False
        self.interrupted: bool = False

        # Resume state
        self.resume_run_id: Optional[int] = None
        self.resume_failed_only: bool = False
        self.previous_job_statuses: Dict[str, str] = {}

    def initialize_run(self) -> int:
        """
        Initialize a new execution run.

        Returns:
            The new run ID
        """
        self.run_id = self.job_history.get_new_run_id()
        self.job_history.run_id = self.run_id
        self.logger.info(f"Initialized new run with ID: {self.run_id}")
        return self.run_id

    def start_execution(self, continue_on_error: bool = False, dry_run: bool = False, working_dir: str = None) -> None:
        """
        Start the execution by recording start time and creating run summary.

        Args:
            continue_on_error: Whether to continue execution on job failures
            dry_run: Whether this is a dry run (no actual execution)
            working_dir: Working directory for this execution run
        """
        self.continue_on_error = continue_on_error
        self.dry_run = dry_run
        self.start_time = datetime.datetime.now()
        self.exit_code = 0
        self.interrupted = False

        # Create run summary entry for actual runs
        if not dry_run and self.run_id is not None:
            try:
                self.job_history.create_run_summary(
                    self.run_id,
                    self.application_name,
                    self.start_time,
                    len(self.jobs),
                    working_dir
                )
                self.logger.info(f"Created run summary for run ID: {self.run_id}")
            except Exception as e:
                # Run summary may already exist if resuming or re-running
                self.logger.debug(f"Run summary may already exist for run ID {self.run_id}: {e}")

    def finish_execution(self, completed_jobs: Set[str], failed_jobs: Set[str], skipped_jobs: Set[str]) -> None:
        """
        Finish the execution by recording end time and updating run summary.

        Args:
            completed_jobs: Set of successfully completed job IDs
            failed_jobs: Set of failed job IDs
            skipped_jobs: Set of skipped job IDs
        """
        self.end_time = datetime.datetime.now()

        # Determine final status
        status = "SUCCESS" if self.exit_code == 0 else "FAILED"

        # Check for incomplete jobs
        all_job_ids = set(self.jobs.keys())
        processed_jobs = completed_jobs | failed_jobs | skipped_jobs
        not_completed = all_job_ids - processed_jobs

        if not_completed:
            self.logger.warning(f"The following jobs were not completed: {', '.join(not_completed)}")
            self.exit_code = 1
            status = "FAILED"

        # Update run summary for actual runs
        if not self.dry_run and self.run_id is not None:
            self.job_history.update_run_summary(
                self.run_id,
                self.end_time,
                status,
                len(completed_jobs),
                len(failed_jobs),
                len(skipped_jobs),
                self.exit_code
            )
            self.logger.info(f"Updated run summary for run ID: {self.run_id} with status: {status}")

    def setup_resume(self, resume_run_id: int, resume_failed_only: bool = False) -> Dict[str, str]:
        """
        Setup resume functionality by loading previous run status.

        Args:
            resume_run_id: Run ID to resume from
            resume_failed_only: Whether to only retry failed jobs

        Returns:
            Dictionary mapping job IDs to their previous status
        """
        self.resume_run_id = resume_run_id
        self.resume_failed_only = resume_failed_only

        # Load previous run status
        self.previous_job_statuses = self.job_history.get_previous_run_status(resume_run_id)

        if not self.previous_job_statuses:
            self.logger.error(f"No job history found for run ID {resume_run_id}. Starting fresh.")
            return {}

        resume_mode = "failed jobs only" if resume_failed_only else "all incomplete jobs"
        self.logger.info(f"Resuming from run ID {resume_run_id} ({resume_mode})")

        return self.previous_job_statuses.copy()

    def determine_jobs_to_skip(self) -> Set[str]:
        """
        Determine which jobs should be skipped based on resume settings.

        Returns:
            Set of job IDs that should be skipped
        """
        jobs_to_skip: Set[str] = set()

        if not self.previous_job_statuses:
            return jobs_to_skip

        for job_id, status in self.previous_job_statuses.items():
            if job_id not in self.jobs:
                continue

            if status == "SUCCESS":
                # Always skip successful jobs
                jobs_to_skip.add(job_id)
                self.logger.info(f"Skipping previously successful job: {job_id}")
            elif self.resume_failed_only and status in ["FAILED", "ERROR", "TIMEOUT"]:
                # In failed-only mode, re-run failed jobs
                self.logger.info(f"Will re-run previously failed job: {job_id}")
            elif not self.resume_failed_only and status not in ["FAILED", "ERROR", "TIMEOUT"]:
                # In normal resume mode, skip non-failed jobs
                jobs_to_skip.add(job_id)
                self.logger.info(f"Skipping job with status {status}: {job_id}")

        return jobs_to_skip

    def mark_interrupted(self) -> None:
        """Mark the execution as interrupted."""
        self.interrupted = True
        self.logger.info("Execution marked as interrupted")

    def set_exit_code(self, code: int) -> None:
        """Set the exit code for the execution."""
        self.exit_code = code
        if code != 0:
            self.logger.warning(f"Exit code set to: {code}")

    def get_duration(self) -> Optional[datetime.timedelta]:
        """
        Get the execution duration.

        Returns:
            Duration as timedelta if both start and end times are set, None otherwise
        """
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None

    def get_duration_string(self) -> str:
        """
        Get the execution duration as a formatted string.

        Returns:
            Duration string in format "H:MM:SS" or "N/A" if not available
        """
        duration = self.get_duration()
        if duration:
            return str(duration).split('.')[0]  # Remove microseconds
        return "N/A"

    def get_run_status(self) -> str:
        """
        Get the current run status.

        Returns:
            "SUCCESS" if exit code is 0, "FAILED" otherwise
        """
        return "SUCCESS" if self.exit_code == 0 else "FAILED"

    def is_dry_run(self) -> bool:
        """Check if this is a dry run."""
        return self.dry_run

    def is_interrupted(self) -> bool:
        """Check if execution was interrupted."""
        return self.interrupted

    def should_continue_on_error(self) -> bool:
        """Check if execution should continue on errors."""
        return self.continue_on_error

    def get_resume_info(self) -> Dict[str, Any]:
        """
        Get resume information for display.

        Returns:
            Dictionary with resume information
        """
        return {
            "resume_run_id": self.resume_run_id,
            "resume_failed_only": self.resume_failed_only,
            "previous_job_count": len(self.previous_job_statuses),
            "has_previous_jobs": bool(self.previous_job_statuses)
        }

    def get_timing_info(self) -> Dict[str, Any]:
        """
        Get timing information for display.

        Returns:
            Dictionary with timing information
        """
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.get_duration(),
            "duration_string": self.get_duration_string(),
            "start_time_str": self.start_time.strftime('%Y-%m-%d %H:%M:%S') if self.start_time else "N/A",
            "end_time_str": self.end_time.strftime('%Y-%m-%d %H:%M:%S') if self.end_time else "N/A"
        }

    def commit_job_statuses(self) -> None:
        """Commit any pending job status updates to persistence."""
        self.job_history.commit_job_statuses()
        self.logger.debug("Committed job statuses to persistence")

    def validate_state(self) -> bool:
        """
        Validate the current state for consistency.

        Returns:
            True if state is valid, False otherwise
        """
        if self.run_id is None:
            self.logger.error("Invalid state: run_id is None")
            return False

        if self.start_time and self.end_time and self.start_time > self.end_time:
            self.logger.error("Invalid state: start_time is after end_time")
            return False

        return True

