"""
Summary Reporter for execution results.

This module provides the SummaryReporter class that handles:
- Execution summary display formatting
- Failed and skipped job reporting
- Resume instruction generation
- Run information display
"""

from typing import Dict, List, Set, Tuple
from config.loader import Config


class SummaryReporter:
    """
    Handles execution summary reporting and display formatting.
    
    This class encapsulates all logic for displaying execution results,
    failed job details, resume instructions, and run information.
    """
    
    def __init__(self, application_name: str, config_file: str):
        """
        Initialize the SummaryReporter.
        
        Args:
            application_name: Name of the application being executed
            config_file: Path to the configuration file
        """
        self.application_name = application_name
        self.config_file = config_file

    def print_execution_summary(
        self, 
        run_id: int, 
        status: str, 
        start_time_str: str, 
        end_time_str: str, 
        duration_str: str,
        completed_jobs: Set[str], 
        failed_jobs: Set[str], 
        skip_jobs: Set[str],
        exit_code: int
    ) -> None:
        """Print the main execution summary header."""
        status_color = Config.COLOR_DARK_GREEN if exit_code == 0 else Config.COLOR_RED
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}{'EXECUTION SUMMARY':^40}{Config.COLOR_RESET}")
        print(f"{divider}")
        print(f"{Config.COLOR_CYAN}Application:{Config.COLOR_RESET} {self.application_name}")
        print(f"{Config.COLOR_CYAN}Run ID:{Config.COLOR_RESET} {Config.COLOR_YELLOW}{run_id}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Status:{Config.COLOR_RESET} {status_color}{status}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Start Time:{Config.COLOR_RESET} {start_time_str}")
        print(f"{Config.COLOR_CYAN}End Time:{Config.COLOR_RESET} {end_time_str}")
        print(f"{Config.COLOR_CYAN}Duration:{Config.COLOR_RESET} {duration_str}")
        print(f"{Config.COLOR_CYAN}Jobs Completed:{Config.COLOR_RESET} {Config.COLOR_DARK_GREEN}{len(completed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Failed:{Config.COLOR_RESET} {Config.COLOR_RED if len(failed_jobs) > 0 else ''}{len(failed_jobs)}{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}Jobs Skipped:{Config.COLOR_RESET} {Config.COLOR_YELLOW if len(skip_jobs) > 0 else ''}{len(skip_jobs)}{Config.COLOR_RESET}")

    def calculate_skipped_due_to_deps(
        self, 
        jobs: Dict[str, Dict], 
        completed_jobs: Set[str], 
        failed_jobs: Set[str], 
        skip_jobs: Set[str],
        dependency_manager
    ) -> List[Tuple[str, List[str], List[str]]]:
        """Calculate jobs skipped due to unmet dependencies."""
        skipped_due_to_deps = []
        for job_id in jobs:
            if job_id not in completed_jobs and job_id not in failed_jobs and job_id not in skip_jobs:
                unmet = [dep for dep in dependency_manager.get_job_dependencies(job_id) 
                        if dep not in completed_jobs and dep not in skip_jobs]
                failed_unmet = [dep for dep in unmet if dep in failed_jobs]
                skipped_due_to_deps.append((job_id, unmet, failed_unmet))
        return skipped_due_to_deps

    def print_failed_jobs_summary(
        self, 
        failed_jobs: Set[str], 
        jobs_config: List[Dict], 
        job_log_paths: Dict[str, str], 
        failed_job_reasons: Dict[str, str]
    ) -> None:
        """Print detailed summary of failed jobs."""
        failed_job_order = [j["id"] for j in jobs_config if j["id"] in failed_jobs]
        if not failed_job_order:
            return
            
        print("\nFailed Jobs:")
        for job_id in failed_job_order:
            job_log_path = job_log_paths.get(job_id, None)
            desc = next((j.get('description', '') for j in jobs_config if j.get('id') == job_id), '')
            reason = failed_job_reasons.get(job_id, '')
            print(f"  - {job_id}: {desc}\n      Reason: {reason}")
            if job_log_path:
                print(f"      Log: {job_log_path}")

    def print_skipped_jobs_summary(
        self, 
        skipped_due_to_deps: List[Tuple[str, List[str], List[str]]], 
        jobs: Dict[str, Dict]
    ) -> None:
        """Print detailed summary of skipped jobs."""
        if not skipped_due_to_deps:
            return
            
        print("\nSkipped Jobs (unmet dependencies):")
        for job_id, unmet, failed_unmet in skipped_due_to_deps:
            desc = jobs[job_id].get('description', '')
            if failed_unmet:
                print(f"  - {job_id}: {desc}\n      Skipped (failed dependencies: {', '.join(failed_unmet)}; other unmet: {', '.join([d for d in unmet if d not in failed_unmet])})")
            else:
                print(f"  - {job_id}: {desc}\n      Skipped (unmet dependencies: {', '.join(unmet)})")

    def print_resume_instructions(
        self, 
        run_id: int, 
        exit_code: int, 
        failed_job_order: List[str], 
        has_skipped_deps: bool
    ) -> None:
        """Print resume instructions for failed runs."""
        if exit_code == 0:
            self._print_successful_run_info(run_id)
            return
            
        if not (failed_job_order or has_skipped_deps):
            return
            
        print(f"\n{Config.COLOR_CYAN}RESUME OPTIONS:{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}{'='*len('RESUME OPTIONS:')}{Config.COLOR_RESET}")
        
        print(f"To resume this run (all incomplete jobs):")
        print(f"  {Config.COLOR_BLUE}executioner.py -c {self.config_file} --resume-from {run_id}{Config.COLOR_RESET}")
        
        if failed_job_order:
            print(f"\nTo retry only failed jobs:")
            print(f"  {Config.COLOR_BLUE}executioner.py -c {self.config_file} --resume-from {run_id} --resume-failed-only{Config.COLOR_RESET}")
            
            # Suggest mark-success for manual fixes
            print(f"\nIf you manually fixed and ran any failed jobs:")
            print(f"  {Config.COLOR_BLUE}executioner.py --mark-success -r {run_id} -j <job_id>{Config.COLOR_RESET}")
            print(f"  Example: executioner.py --mark-success -r {run_id} -j {failed_job_order[0]}")
        
        print(f"\nTo see detailed job status:")
        print(f"  {Config.COLOR_BLUE}executioner.py --show-run {run_id}{Config.COLOR_RESET}")

    def _print_successful_run_info(self, run_id: int) -> None:
        """Print run information for successful executions."""
        print(f"\n{Config.COLOR_CYAN}RUN INFORMATION:{Config.COLOR_RESET}")
        print(f"{Config.COLOR_CYAN}{'='*len('RUN INFORMATION:')}{Config.COLOR_RESET}")
        print(f"To view detailed job status for this run:")
        print(f"  {Config.COLOR_BLUE}executioner.py --show-run {run_id}{Config.COLOR_RESET}")
        print(f"\nTo list all recent runs for {self.application_name}:")
        print(f"  {Config.COLOR_BLUE}executioner.py --list-runs {self.application_name}{Config.COLOR_RESET}")
        print(f"\nTo list all recent runs (all applications):")
        print(f"  {Config.COLOR_BLUE}executioner.py --list-runs{Config.COLOR_RESET}")

    def print_final_divider(self) -> None:
        """Print the final summary divider."""
        divider = f"{Config.COLOR_CYAN}{'='*40}{Config.COLOR_RESET}"
        print(f"{divider}")
        print("\n")