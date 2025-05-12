"""
job.py - Job abstraction for the Executioner system.
"""

class Job:
    """
    Represents a single job in the execution pipeline.
    Handles job state, execution, pre/post checks, and environment.
    """
    def __init__(self, job_config, global_env=None, logger=None):
        self.job_config = job_config
        self.global_env = global_env or {}
        self.logger = logger
        self.status = None
        self.result = None

    def run(self):
        """Run the job's main command."""
        pass

    def run_pre_checks(self):
        """Run pre-checks for the job."""
        pass

    def run_post_checks(self):
        """Run post-checks for the job."""
        pass 