"""
Queue Manager for handling job queuing logic and state tracking.

This module provides the QueueManager class that handles:
- Job queue operations
- Job state tracking (completed, failed, active, queued)
- Dependency-based job queuing
- Thread-safe state management
"""

import threading
import logging
from queue import Queue, Empty
from typing import Dict, Set, List, Optional
from concurrent.futures import Future

from jobs.dependency_manager import DependencyManager


class QueueManager:
    """
    Manages job queuing, state tracking, and dependency-based scheduling.
    
    This class encapsulates all queue-related operations and job state management,
    providing thread-safe access to job states and queue operations.
    """
    
    def __init__(self, dependency_manager: DependencyManager, logger: logging.Logger):
        """
        Initialize the QueueManager.
        
        Args:
            dependency_manager: Manager for handling job dependencies
            logger: Logger instance for debug/info messages
        """
        self.dependency_manager = dependency_manager
        self.logger = logger
        
        # Threading primitives
        self.lock = threading.RLock()
        self.job_completed_condition = threading.Condition()
        
        # Job queue and state tracking
        self.job_queue: Queue = Queue()
        self.completed_jobs: Set[str] = set()
        self.failed_jobs: Set[str] = set()
        self.failed_job_reasons: Dict[str, str] = {}
        self.queued_jobs: Set[str] = set()
        self.active_jobs: Set[str] = set()
        self.skip_jobs: Set[str] = set()
        
        # Future tracking for parallel execution
        self.future_to_job_id: Dict[Future, str] = {}
    
    def set_skip_jobs(self, skip_jobs: Set[str]) -> None:
        """Set the jobs that should be skipped."""
        with self.lock:
            self.skip_jobs = skip_jobs.copy()
    
    def add_completed_job(self, job_id: str) -> None:
        """Mark a job as completed."""
        with self.lock:
            self.completed_jobs.add(job_id)
            self.active_jobs.discard(job_id)
    
    def add_failed_job(self, job_id: str, reason: Optional[str] = None) -> None:
        """Mark a job as failed with optional reason."""
        with self.lock:
            self.failed_jobs.add(job_id)
            self.active_jobs.discard(job_id)
            if reason:
                self.failed_job_reasons[job_id] = reason
    
    def add_active_job(self, job_id: str) -> None:
        """Mark a job as active (currently running)."""
        with self.lock:
            self.active_jobs.add(job_id)
            self.queued_jobs.discard(job_id)
    
    def queue_job(self, job_id: str) -> None:
        """Add a job to the queue."""
        with self.lock:
            if job_id not in self.queued_jobs:
                self.job_queue.put(job_id)
                self.queued_jobs.add(job_id)
                self.logger.debug(f"Queued job: {job_id}")
    
    def get_next_job(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        Get the next job from the queue.
        
        Args:
            timeout: Optional timeout for queue get operation
            
        Returns:
            Job ID if available, None if queue is empty or timeout
        """
        try:
            if timeout is not None:
                return self.job_queue.get(timeout=timeout)
            else:
                return self.job_queue.get_nowait()
        except Empty:
            return None
    
    def is_queue_empty(self) -> bool:
        """Check if the job queue is empty."""
        return self.job_queue.empty()
    
    def get_queue_size(self) -> int:
        """Get the current size of the job queue."""
        return self.job_queue.qsize()
    
    def is_job_ready(self, job_id: str) -> bool:
        """
        Check if a job is ready to run (all dependencies satisfied).
        
        Args:
            job_id: ID of the job to check
            
        Returns:
            True if job is ready to run, False otherwise
        """
        with self.lock:
            if (job_id in self.skip_jobs or
                job_id in self.completed_jobs or
                job_id in self.active_jobs or
                job_id in self.failed_jobs):
                return False
            
            deps = self.dependency_manager.get_job_dependencies(job_id)
            missing_deps = [dep for dep in deps 
                          if dep not in self.completed_jobs and dep not in self.skip_jobs]
            return len(missing_deps) == 0
    
    def queue_initial_jobs(self) -> None:
        """Queue all jobs that have no unsatisfied dependencies."""
        with self.lock:
            for job_id, deps in self.dependency_manager.get_all_dependencies().items():
                if job_id in self.skip_jobs:
                    continue
                all_deps_satisfied = all(dep in self.completed_jobs or dep in self.skip_jobs 
                                       for dep in deps)
                if all_deps_satisfied and job_id not in self.queued_jobs:
                    self.queue_job(job_id)
                    self.logger.debug(f"Initially queuing job: {job_id}")
    
    def queue_dependent_jobs(self, completed_job_id: str, dry_run: bool = False) -> None:
        """
        Queue jobs that depend on the completed job.
        
        Args:
            completed_job_id: ID of the job that just completed
            dry_run: If True, skip actual queuing (for dry run mode)
        """
        if dry_run:
            return
            
        with self.lock:
            self.logger.debug(f"Queueing jobs dependent on {completed_job_id}")
            
            # Take snapshots to avoid state changes during iteration
            completed_jobs_snapshot = self.completed_jobs.copy()
            failed_jobs_snapshot = self.failed_jobs.copy()
            skip_jobs_snapshot = self.skip_jobs.copy()
            active_jobs_snapshot = self.active_jobs.copy()
            queued_jobs_snapshot = self.queued_jobs.copy()
            
            jobs_to_queue = []
            
            for job_id, deps in self.dependency_manager.get_all_dependencies().items():
                # Skip if completed job is not a dependency
                if completed_job_id not in deps:
                    continue
                
                # Skip if job is already processed or in progress
                if (job_id in completed_jobs_snapshot or
                    job_id in queued_jobs_snapshot or
                    job_id in active_jobs_snapshot or
                    job_id in skip_jobs_snapshot or
                    job_id in failed_jobs_snapshot):
                    continue
                
                # Check if all dependencies are satisfied
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
                
                # Skip jobs with failed dependencies
                if has_failed_deps:
                    continue
                
                # Queue job if all dependencies are satisfied
                if all_deps_satisfied:
                    jobs_to_queue.append(job_id)
                    self.queued_jobs.add(job_id)
            
            # Queue all eligible jobs
            for job_id in jobs_to_queue:
                self.job_queue.put(job_id)
                self.logger.debug(f"Queued dependent job: {job_id}")
            
            # Notify waiting threads
            with self.job_completed_condition:
                self.job_completed_condition.notify_all()
    
    def register_future(self, future: Future, job_id: str) -> None:
        """Register a future with its corresponding job ID."""
        with self.lock:
            self.future_to_job_id[future] = job_id
    
    def unregister_future(self, future: Future) -> Optional[str]:
        """Unregister a future and return its job ID."""
        with self.lock:
            return self.future_to_job_id.pop(future, None)
    
    def get_status_summary(self) -> Dict[str, int]:
        """
        Get a summary of job status counts.
        
        Returns:
            Dictionary with counts for each job status
        """
        with self.lock:
            return {
                'completed': len(self.completed_jobs),
                'failed': len(self.failed_jobs),
                'active': len(self.active_jobs),
                'queued': len(self.queued_jobs),
                'skipped': len(self.skip_jobs)
            }
    
    def get_failed_job_reasons(self) -> Dict[str, str]:
        """Get a copy of failed job reasons."""
        with self.lock:
            return self.failed_job_reasons.copy()
    
    def cleanup_future(self, future: Future) -> None:
        """Clean up future tracking and job state."""
        with self.lock:
            job_id = self.future_to_job_id.pop(future, None)
            if job_id:
                self.active_jobs.discard(job_id)