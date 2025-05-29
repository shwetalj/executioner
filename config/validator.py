from config.loader import Config
import sys
from jobs.config_utils import handle_config_errors
from jobs.env_utils import validate_env_vars

def validate_config(config, logger):
    """Validate configuration against a basic schema."""
    with handle_config_errors(logger):
        if "jobs" not in config or not isinstance(config["jobs"], list):
            logger.error("Configuration is missing required 'jobs' list or 'jobs' is not a list")
            raise KeyError("Missing or invalid 'jobs' list")
        
        # Validate application-level environment variables
        if "env_variables" in config:
            is_valid, errors = validate_env_vars(config["env_variables"], logger)
            if not is_valid:
                for error in errors:
                    logger.error(f"Application env_variables: {error}")
                raise ValueError("Invalid application-level environment variables")
        
        # Check for duplicate job IDs
        job_ids = []
        for job in config["jobs"]:
            if isinstance(job, dict) and "id" in job:
                job_ids.append(job["id"])
        
        if len(job_ids) != len(set(job_ids)):
            # Find duplicates for better error message
            seen = set()
            duplicates = set()
            for job_id in job_ids:
                if job_id in seen:
                    duplicates.add(job_id)
                seen.add(job_id)
            logger.error(f"Duplicate job IDs found in configuration: {', '.join(duplicates)}")
            raise ValueError(f"Duplicate job IDs detected: {', '.join(duplicates)}")

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
            if "env_variables" in job:
                if not isinstance(job["env_variables"], dict):
                    logger.error(f"Job '{job['id']}' has invalid env_variables")
                    raise TypeError(f"Job '{job['id']}' has invalid env_variables")
                # Validate job-level environment variables
                is_valid, errors = validate_env_vars(job["env_variables"], logger)
                if not is_valid:
                    for error in errors:
                        logger.error(f"Job '{job['id']}' env_variables: {error}")
                    raise ValueError(f"Job '{job['id']}' has invalid environment variables")
            if "dependencies" in job and not isinstance(job["dependencies"], list):
                logger.error(f"Job '{job['id']}' has invalid dependencies")
                raise TypeError(f"Job '{job['id']}' has invalid dependencies") 