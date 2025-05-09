from jobs.checks import CHECK_REGISTRY
import datetime

def run_checks(checks, job_logger, phase="pre", job_id=None):
    """
    Run a list of checks (pre or post) for a job.
    Returns True if all checks pass, False otherwise.
    Logs results to the provided job_logger.
    """
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