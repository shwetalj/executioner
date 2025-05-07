from config.loader import Config
import sys

def validate_config(config, logger):
    """Validate configuration against a basic schema."""
    if "jobs" not in config or not isinstance(config["jobs"], list):
        logger.error("Configuration is missing required 'jobs' list or 'jobs' is not a list")
        sys.exit(1)

    for i, job in enumerate(config["jobs"]):
        if not isinstance(job, dict):
            logger.error(f"Job at index {i} is not a dictionary")
            sys.exit(1)
        if "id" not in job or not isinstance(job["id"], str):
            logger.error(f"Job at index {i} is missing or has invalid 'id' field")
            sys.exit(1)
        if "command" not in job or not isinstance(job["command"], str):
            logger.error(f"Job '{job.get('id', f'at index {i}')}' is missing or has invalid 'command' field")
            sys.exit(1)
        if "timeout" in job and (not isinstance(job["timeout"], (int, float)) or job["timeout"] <= 0):
            logger.warning(f"Job '{job['id']}' has invalid timeout: {job['timeout']}. Using default.")
            job["timeout"] = Config.DEFAULT_TIMEOUT
        if "env_variables" in job and not isinstance(job["env_variables"], dict):
            logger.error(f"Job '{job['id']}' has invalid env_variables")
            sys.exit(1)
        if "dependencies" in job and not isinstance(job["dependencies"], list):
            logger.error(f"Job '{job['id']}' has invalid dependencies")
            sys.exit(1) 