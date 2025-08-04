class JobStatusMixin:
    """
    Mixin to provide common job status and retry logic.
    Assumes the class using this mixin has:
      - self.job_history (ExecutionHistoryManager)
      - self.logger
    """

    def mark_success(self, job_id, duration=None, start_time=None):
        self.job_history.update_job_status(job_id, "SUCCESS", duration=duration, start_time=start_time)

    def mark_failed(self, job_id, reason=None, duration=None, start_time=None):
        self.job_history.update_job_status(job_id, "FAILED", duration=duration, start_time=start_time)

    def mark_error(self, job_id, reason=None, duration=None, start_time=None):
        self.job_history.update_job_status(job_id, "ERROR", duration=duration, start_time=start_time)

    def mark_timeout(self, job_id, duration=None, start_time=None):
        self.job_history.update_job_status(job_id, "TIMEOUT", duration=duration, start_time=start_time)

    def mark_blocked(self, job_id, reason=None):
        self.job_history.update_job_status(job_id, "BLOCKED")

    def record_retry(self, job_id, retry_history, retry_count, status, reason=None):
        self.job_history.update_retry_history(job_id, retry_history, retry_count, status, reason)
        # Optionally log retry info if needed

    def should_retry(self, job, last_status, retry_count):
        retry_on_status = job.get("retry_on_status", ["ERROR", "FAILED", "TIMEOUT"])
        max_retries = job.get("max_retries", 0)
        return last_status in retry_on_status and retry_count < max_retries

