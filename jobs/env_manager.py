def merge_env_vars(app_env, job_env):
    """
    Merge application-level and job-level environment variables.
    Job-level variables take precedence. All values are converted to strings.
    """
    merged = {k: str(v) for k, v in (app_env or {}).items()}
    for k, v in (job_env or {}).items():
        merged[k] = str(v)
    return merged

# Optionally, add validation or expansion logic here in the future.

def validate_env_vars(env_vars):
    """
    Placeholder for environment variable validation logic.
    """
    # Example: check for reserved keys, invalid names, etc.
    return True 