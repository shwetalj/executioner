from config.loader import Config
import sys
from jobs.config_utils import handle_config_errors

def validate_config(config, logger):
    """Validate configuration against a basic schema."""
    with handle_config_errors(logger):
        if "jobs" not in config or not isinstance(config["jobs"], list):
            logger.error("Configuration is missing required 'jobs' list or 'jobs' is not a list")
            raise KeyError("Missing or invalid 'jobs' list")

        for i, job in enumerate(config["jobs"]):
            if not isinstance(job, dict):
                logger.error(f"Job at index {i} is not a dictionary")
                raise TypeError(f"Job at index {i} is not a dictionary")
            if "id" not in job or not isinstance(job["id"], str):
                logger.error(f"Job at index {i} is missing or has invalid 'id' field")
                raise KeyError(f"Job at index {i} is missing or has invalid 'id' field")
            if "command" not in job or not isinstance(job["command"], str):
                logger.error(f"Job '{job.get('id', f'at index {i}')}' is missing or has invalid 'command' field")
                raise KeyError(f"Job '{job.get('id', f'at index {i}')}' is missing or has invalid 'command' field")
            if "timeout" in job and (not isinstance(job["timeout"], (int, float)) or job["timeout"] <= 0):
                logger.warning(f"Job '{job['id']}' has invalid timeout: {job['timeout']}. Using default.")
                job["timeout"] = Config.DEFAULT_TIMEOUT
            if "env_variables" in job and not isinstance(job["env_variables"], dict):
                logger.error(f"Job '{job['id']}' has invalid env_variables")
                raise TypeError(f"Job '{job['id']}' has invalid env_variables")
            if "dependencies" in job and not isinstance(job["dependencies"], list):
                logger.error(f"Job '{job['id']}' has invalid dependencies")
                raise TypeError(f"Job '{job['id']}' has invalid dependencies") 