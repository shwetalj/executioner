"""
Execution Orchestrator for handling execution flow and coordination.

This module provides the ExecutionOrchestrator class that handles:
- Sequential and parallel execution strategies
- Dependency resolution and execution ordering  
- Dry run execution planning and display
- Job queuing coordination with QueueManager
- Execution flow control and monitoring
"""

import threading
import logging
import signal
import time
from typing import Dict, Set, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
import concurrent.futures

from config.loader import Config
from jobs.queue_manager import QueueManager
from jobs.state_manager import StateManager
from jobs.dependency_manager import DependencyManager


class ExecutionOrchestrator:
    """
    Handles execution orchestration, flow control, and dependency resolution.
    
    This class encapsulates all execution logic including sequential/parallel execution,
    dry run planning, and coordination between QueueManager and StateManager.
    """
    
    def __init__(
        self,
        jobs: Dict[str, Dict],
        queue_manager: QueueManager,
        state_manager: StateManager,
        dependency_manager: DependencyManager,
        logger: logging.Logger,
        execute_job_func: Any,  # Function type for job execution
        application_name: str,
        max_workers: int = 1,
        parallel: bool = False
    ):
        """
        Initialize the ExecutionOrchestrator.
        
        Args:
            jobs: Dictionary of job configurations
            queue_manager: QueueManager for job state tracking
            state_manager: StateManager for execution lifecycle
            dependency_manager: DependencyManager for dependency resolution
            logger: Logger instance
            execute_job_func: Function to execute individual jobs
            application_name: Name of the application
            max_workers: Maximum number of parallel workers
            parallel: Whether to use parallel execution
        """
        self.jobs = jobs
        self.queue_manager = queue_manager
        self.state_manager = state_manager
        self.dependency_manager = dependency_manager
        self.logger = logger
        self.execute_job = execute_job_func
        self.application_name = application_name
        self.max_workers = max_workers if max_workers > 0 else 1
        self.parallel = parallel
        
        # Threading primitives for parallel execution
        self.executor: Optional[ThreadPoolExecutor] = None
    
    def run_dry(self, resume_run_id: Optional[int] = None, resume_failed_only: bool = False) -> int:
        """
        Execute a dry run showing the execution plan without running jobs.
        
        Args:
            resume_run_id: Optional run ID to resume from
            resume_failed_only: Whether to only retry failed jobs in resume mode
            
        Returns:
            Exit code (0 for success)
        """
        self.state_manager.start_execution(continue_on_error=False, dry_run=True)
        self.logger.info(f"Starting dry run - printing execution plan")
        
        # Handle resume functionality for dry run
        if resume_run_id:
            previous_job_statuses = self.state_manager.setup_resume(resume_run_id, resume_failed_only)
            if not previous_job_statuses:
                self.logger.error(f"No job history found for run ID {resume_run_id}. Showing full plan.")
            else:
                resume_mode = "failed jobs only" if resume_failed_only else "all incomplete jobs"
                self.logger.info(f"Resuming from run ID {resume_run_id} ({resume_mode})")
                
                # Apply resume logic to determine skip jobs
                resume_skip_jobs = self.state_manager.determine_jobs_to_skip()
                self.queue_manager.set_skip_jobs(resume_skip_jobs)
                
                # Log what would be skipped/executed
                for job_id, status in previous_job_statuses.items():
                    if job_id not in self.jobs:
                        continue
                    if status == "SUCCESS":
                        self.logger.info(f"Would skip previously successful job: {job_id}")
                    elif resume_failed_only and status in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.logger.info(f"Would re-run previously failed job: {job_id}")
                    elif not resume_failed_only and status not in ["FAILED", "ERROR", "TIMEOUT"]:
                        self.logger.info(f"Would skip job with status {status}: {job_id}")
        
        # Validate dependencies
        if self.dependency_manager.has_circular_dependencies():
            self.logger.error("Circular dependencies detected in job configuration")
            print(f"{Config.COLOR_RED}ERROR: Circular dependencies detected{Config.COLOR_RESET}")
            return 1
        
        missing_dependencies = self.dependency_manager.check_missing_dependencies()
        if missing_dependencies:
            for job_id, missing_deps in missing_dependencies.items():
                msg = f"Job '{job_id}' has missing dependencies: {', '.join(missing_deps)}"
                self.logger.error(msg)
                print(f"{Config.COLOR_RED}ERROR: {msg}{Config.COLOR_RESET}")
            
            if not self.state_manager.should_continue_on_error():
                self.logger.error("Missing dependencies detected. Would abort.")
                print(f"{Config.COLOR_RED}ERROR: Missing dependencies detected{Config.COLOR_RESET}")
                return 1
            print(f"{Config.COLOR_YELLOW}WARNING: Missing dependencies detected but would continue{Config.COLOR_RESET}")
        
        # Display execution plan
        self._display_execution_plan()
        
        # Display dry run summary
        self._display_dry_run_summary()
        
        self.logger.info(f"Dry run completed for run ID: {self.state_manager.run_id}")
        return 0
    
    def run_sequential(self, max_iter: int = 1000) -> int:
        """
        Execute jobs sequentially with dependency resolution.
        
        Args:
            max_iter: Maximum iterations to prevent infinite loops
            
        Returns:
            Number of iterations performed
        """
        iteration_count = 0
        
        while not self.queue_manager.is_queue_empty() and iteration_count < max_iter and not self.state_manager.is_interrupted():
            iteration_count += 1
            
            job_id = self.queue_manager.get_next_job(timeout=1)
            if job_id is None:
                break
            
            if job_id in self.queue_manager.skip_jobs or job_id in self.queue_manager.completed_jobs:
                continue
            
            # Verify dependencies are still satisfied
            deps = self.dependency_manager.get_job_dependencies(job_id)
            missing_deps = [dep for dep in deps 
                          if dep not in self.queue_manager.completed_jobs and dep not in self.queue_manager.skip_jobs]
            
            if missing_deps:
                if all(dep in self.jobs for dep in missing_deps):
                    self.logger.warning(f"Job {job_id} queued before dependencies were satisfied: {missing_deps}")
                    continue
                
                self.logger.warning(f"Job {job_id} has non-existent dependencies: {missing_deps}")
                if self.state_manager.should_continue_on_error():
                    self.logger.warning(f"Skipping job {job_id} due to missing dependencies")
                    self.queue_manager.add_failed_job(job_id, f"Missing dependencies: {', '.join(missing_deps)}")
                    continue
                
                self.logger.error(f"Job {job_id} has missing dependencies. Stopping.")
                self.queue_manager.add_failed_job(job_id, f"Missing dependencies: {', '.join(missing_deps)}")
                self.state_manager.set_exit_code(1)
                break
            
            # Execute the job
            job_success, fail_reason = self.execute_job(job_id)
            
            if self.state_manager.is_interrupted():
                self.logger.info("Execution interrupted, stopping gracefully.")
                break
            
            # Update job state
            with self.queue_manager.lock:
                if job_success:
                    self.queue_manager.add_completed_job(job_id)
                else:
                    self.queue_manager.add_failed_job(job_id, fail_reason or "Unknown failure")
                    if not self.state_manager.should_continue_on_error():
                        self.state_manager.set_exit_code(1)
                        break
                    self.logger.warning(f"Job {job_id} failed but continuing.")
            
            # Queue dependent jobs if this job succeeded
            if job_success:
                self.queue_manager.queue_dependent_jobs(job_id, self.state_manager.is_dry_run())
        
        return iteration_count
    
    def run_parallel(self, max_iter: int = 1000) -> int:
        """
        Execute jobs in parallel with dependency resolution.
        
        Args:
            max_iter: Maximum iterations to prevent infinite loops
            
        Returns:
            Number of iterations performed
        """
        iteration_count = 0
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        self.logger.info(f"Parallel execution with {self.max_workers} workers")
        
        pending_futures: Set[Future] = set()
        
        try:
            while ((not self.queue_manager.is_queue_empty() or pending_futures) 
                   and iteration_count < max_iter 
                   and not self.state_manager.is_interrupted()):
                
                iteration_count += 1
                just_completed_jobs: Set[str] = set()
                
                # Process completed futures
                try:
                    completed_futures = list(as_completed(pending_futures, timeout=0.1))
                    for future in completed_futures:
                        pending_futures.remove(future)
                        
                        with self.queue_manager.lock:
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
                                    if not self.state_manager.should_continue_on_error():
                                        self.state_manager.set_exit_code(1)
                                        self.state_manager.mark_interrupted()
                                    else:
                                        self.logger.warning(f"Job {job_id} failed but continuing.")
                            except Exception as e:
                                self.logger.error(f"Job {job_id} raised exception: {e}")
                                self.queue_manager.add_failed_job(job_id, f"Exception: {e}")
                                if not self.state_manager.should_continue_on_error():
                                    self.state_manager.set_exit_code(1)
                                    self.state_manager.mark_interrupted()
                        
                        # Notify other threads of completion
                        with self.queue_manager.job_completed_condition:
                            self.queue_manager.job_completed_condition.notify_all()
                
                except concurrent.futures.TimeoutError:
                    pass
                
                # Queue dependent jobs for completed jobs
                for job_id in just_completed_jobs:
                    if not self.state_manager.is_interrupted():
                        self.queue_manager.queue_dependent_jobs(job_id, self.state_manager.is_dry_run())
                
                # Submit new jobs
                jobs_queued = 0
                while not self.queue_manager.is_queue_empty() and not self.state_manager.is_interrupted():
                    available_worker_slots = self.max_workers - len(pending_futures)
                    if available_worker_slots <= 0:
                        break
                    
                    job_id = self.queue_manager.get_next_job(timeout=0.1)
                    if job_id is None:
                        break
                    
                    should_submit = False
                    missing_deps = []
                    
                    with self.queue_manager.lock:
                        if (job_id in self.queue_manager.skip_jobs or
                            job_id in self.queue_manager.completed_jobs or
                            job_id in self.queue_manager.active_jobs):
                            continue
                        
                        deps = self.dependency_manager.get_job_dependencies(job_id)
                        missing_deps = [dep for dep in deps 
                                      if dep not in self.queue_manager.completed_jobs and dep not in self.queue_manager.skip_jobs]
                        
                        if not missing_deps:
                            should_submit = True
                            self.queue_manager.add_active_job(job_id)
                    
                    if missing_deps:
                        if all(dep in self.jobs for dep in missing_deps):
                            self.queue_manager.queue_job(job_id)
                            break
                        
                        non_existent_deps = [dep for dep in missing_deps if dep not in self.jobs]
                        self.logger.warning(f"Job {job_id} has non-existent dependencies: {non_existent_deps}")
                        
                        if self.state_manager.should_continue_on_error():
                            continue
                        
                        self.logger.error(f"Job {job_id} has missing dependencies. Stopping.")
                        self.state_manager.set_exit_code(1)
                        self.state_manager.mark_interrupted()
                        break
                    
                    if should_submit:
                        with self.queue_manager.lock:
                            future = self.executor.submit(self.execute_job, job_id)
                            pending_futures.add(future)
                            self.queue_manager.register_future(future, job_id)
                            self.logger.debug(f"Submitted job {job_id}")
                            jobs_queued += 1
                
                # Wait for activity if nothing happened
                if not completed_futures and not jobs_queued:
                    with self.queue_manager.job_completed_condition:
                        self.queue_manager.job_completed_condition.wait(timeout=1.0)
                
                # Periodic status logging
                if iteration_count % 10 == 0:
                    with self.queue_manager.lock:
                        status_summary = self.queue_manager.get_status_summary()
                        self.logger.debug(
                            f"Execution status - Queue: {self.queue_manager.get_queue_size()}, "
                            f"Active: {status_summary['active']}, Completed: {status_summary['completed']}, "
                            f"Failed: {status_summary['failed']}, Skipped: {status_summary['skipped']}"
                        )
            
            # Wait for remaining jobs to complete
            if pending_futures:
                self._wait_for_remaining_jobs(pending_futures)
        
        finally:
            if self.executor:
                self.logger.debug("Shutting down thread pool executor")
                self.executor.shutdown(wait=True)
                self.executor = None
        
        return iteration_count
    
    def _wait_for_remaining_jobs(self, pending_futures: Set[Future]) -> None:
        """Wait for remaining parallel jobs to complete with timeout."""
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
                    with self.queue_manager.lock:
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
        
        # Cancel remaining jobs if timeout exceeded
        if futures_to_wait:
            self.logger.warning(f"Abandoning {len(futures_to_wait)} jobs after {max_wait_time}s")
            with self.queue_manager.lock:
                for future in futures_to_wait:
                    future.cancel()
                    job_id = self.queue_manager.unregister_future(future)
                    if job_id:
                        self.queue_manager.add_failed_job(job_id, "Abandoned during shutdown")
                        pending_futures.discard(future)
                        self.logger.warning(f"Job {job_id} abandoned during shutdown")
    
    def _display_execution_plan(self) -> None:
        """Display the execution plan for dry run."""
        # Execution mode
        parallel_text = f"{Config.COLOR_CYAN}Execution mode:{Config.COLOR_RESET} "
        if self.parallel:
            parallel_text += f"{Config.COLOR_MAGENTA}PARALLEL with {self.max_workers} workers{Config.COLOR_RESET}"
        else:
            parallel_text += f"{Config.COLOR_BLUE}SEQUENTIAL{Config.COLOR_RESET}"
        print(f"\n{parallel_text}")
        
        # Application environment variables
        app_env_vars = getattr(self.state_manager, 'app_env_variables', {})
        if hasattr(self.queue_manager, 'app_env_variables'):
            app_env_vars = self.queue_manager.app_env_variables
        
        if app_env_vars:
            sorted_vars = sorted(app_env_vars.keys())
            print(f"\n{Config.COLOR_CYAN}Application environment variables:{Config.COLOR_RESET}")
            print(f"{Config.COLOR_MAGENTA}{', '.join(sorted_vars)}{Config.COLOR_RESET}")
        
        # Job execution order
        print(f"\n{Config.COLOR_CYAN}Job execution order:{Config.COLOR_RESET}")
        execution_order = self.dependency_manager.get_execution_order()
        
        for i, job_id in enumerate(execution_order):
            job = self.jobs[job_id]
            job_desc = job.get("description", "")
            
            # Environment variables info
            env_vars_info = ""
            if job.get("env_variables"):
                env_vars = ', '.join(job['env_variables'].keys())
                env_vars_info = f" {Config.COLOR_MAGENTA}[ENV: {env_vars}]{Config.COLOR_RESET}"
            
            # Dependencies info
            deps = self.dependency_manager.get_job_dependencies(job_id)
            deps_info = f" {Config.COLOR_CYAN}[DEPS: {', '.join(deps) or 'none'}]{Config.COLOR_RESET}"
            
            # Skip status or command preview
            if job_id in self.queue_manager.skip_jobs:
                print(f"{i+1}. {Config.COLOR_YELLOW}{job_id}{Config.COLOR_RESET} - {job_desc} "
                      f"{Config.COLOR_YELLOW}[SKIPPED]{Config.COLOR_RESET}{env_vars_info}{deps_info}")
            else:
                command = job["command"]
                command_preview = command[:40] + '...' if len(command) > 40 else command
                print(f"{i+1}. {Config.COLOR_DARK_GREEN}{job_id}{Config.COLOR_RESET} - {job_desc} - "
                      f"{Config.COLOR_BLUE}{command_preview}{Config.COLOR_RESET}{env_vars_info}{deps_info}")
    
    def _display_dry_run_summary(self) -> None:
        """Display the dry run execution summary."""
        timing_info = self.state_manager.get_timing_info()
        duration_str = timing_info["duration_string"]
        start_time_str = timing_info["start_time_str"]
        end_time_str = timing_info["end_time_str"]
        
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"\n{divider}")
        print(f"{Config.COLOR_CYAN}{'DRY RUN EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {self.state_manager.run_id}")
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {start_time_str}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_time_str}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} {duration_str}")
        print(f"{Config.COLOR_CYAN}Total Jobs:{Config.COLOR_RESET} {len(self.jobs)}")
        
        skip_count = len(self.queue_manager.skip_jobs)
        execute_count = len(self.jobs) - skip_count
        
        print(f"{Config.COLOR_CYAN}Would Execute:{Config.COLOR_RESET} {Config.COLOR_DARK_GREEN}{execute_count}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Would Skip:{Config.COLOR_RESET} {Config.COLOR_YELLOW if skip_count > 0 else ''}{skip_count}{Config.COLOR_RESET}")
        print(f"{divider}")
        print("\n")
    
    def setup_interrupt_handler(self, dry_run: bool = False) -> Any:
        """
        Setup keyboard interrupt handler.
        
        Args:
            dry_run: Whether this is a dry run
            
        Returns:
            Original signal handler for restoration
        """
        def handle_keyboard_interrupt(signal_num, frame):
            self.state_manager.mark_interrupted()
            self.logger.info("Received interrupt signal. Stopping after current job...")
            if dry_run:
                print("\nInterrupt received. Stopping dry run cleanly...")
            else:
                print("\nInterrupt received. Will stop after current job completes...")
        
        original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, handle_keyboard_interrupt)
        return original_handler
    
    def restore_interrupt_handler(self, original_handler: Any) -> None:
        """Restore the original interrupt handler."""
        signal.signal(signal.SIGINT, original_handler)