from config.loader import Config
import sys
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set
from collections import defaultdict
from jobs.config_utils import handle_config_errors
from jobs.env_utils import validate_env_vars
from jobs.exceptions import ConfigurationError, ValidationError, ErrorCodes

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
        
        # Validate inherit_shell_env setting
        if "inherit_shell_env" in config:
            inherit_setting = config["inherit_shell_env"]
            valid_types = (bool, str, list)
            
            if not isinstance(inherit_setting, valid_types):
                logger.error(f"inherit_shell_env must be boolean, string ('default'), or list of strings")
                raise TypeError("Invalid inherit_shell_env type")
            
            if isinstance(inherit_setting, str) and inherit_setting != "default":
                logger.error(f"inherit_shell_env string value must be 'default', got '{inherit_setting}'")
                raise ValueError("Invalid inherit_shell_env string value")
            
            if isinstance(inherit_setting, list):
                for item in inherit_setting:
                    if not isinstance(item, str):
                        logger.error(f"inherit_shell_env list must contain only strings")
                        raise TypeError("Invalid inherit_shell_env list item type")
        
        # Validate working_dir (now mandatory)
        if "working_dir" not in config:
            logger.error("Configuration is missing required 'working_dir' field")
            raise KeyError("Missing required 'working_dir' field")
        
        working_dir = config["working_dir"]
        if not isinstance(working_dir, str):
            logger.error("working_dir must be a string path")
            raise TypeError("Invalid working_dir type")
        
        # Expand ~ and resolve relative paths
        working_dir_path = Path(working_dir).expanduser()
        if not working_dir_path.is_absolute():
            logger.error(f"working_dir must be an absolute path, got: {working_dir}")
            raise ValueError("working_dir must be absolute path")
        
        # Check if directory exists
        if not working_dir_path.exists():
            logger.error(f"working_dir does not exist: {working_dir_path}")
            raise FileNotFoundError(f"working_dir not found: {working_dir_path}")
        
        if not working_dir_path.is_dir():
            logger.error(f"working_dir is not a directory: {working_dir_path}")
            raise NotADirectoryError(f"working_dir not a directory: {working_dir_path}")
        
        # Check if directory is accessible
        if not os.access(working_dir_path, os.R_OK | os.W_OK):
            logger.error(f"working_dir is not readable/writable: {working_dir_path}")
            raise PermissionError(f"working_dir access denied: {working_dir_path}")
        
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


def validate_job_config(job: Dict[str, Any]) -> List[str]:
    """Validate a single job configuration and return list of errors.
    
    Enhanced validation with better error messages.
    
    Args:
        job: Job configuration dictionary
        
    Returns:
        List of error messages
    """
    errors = []
    
    # Type validations
    if not isinstance(job.get('id'), str):
        errors.append(f"Job ID must be a string, got {type(job.get('id')).__name__}")
    
    if not isinstance(job.get('command'), str):
        errors.append(f"Job command must be a string, got {type(job.get('command')).__name__}")
    
    # Business logic validations
    if job.get('timeout', 0) <= 0:
        errors.append(f"Job {job.get('id', '<unnamed>')}: timeout must be positive")
    
    # Dependency validations
    deps = job.get('dependencies', [])
    if len(deps) != len(set(deps)):
        errors.append(f"Job {job.get('id', '<unnamed>')}: duplicate dependencies found")
    
    # Retry validations
    if 'retry_count' in job and job['retry_count'] < 0:
        errors.append(f"Job {job.get('id', '<unnamed>')}: retry_count cannot be negative")
    
    if 'retry_delay' in job and job['retry_delay'] < 0:
        errors.append(f"Job {job.get('id', '<unnamed>')}: retry_delay cannot be negative")
    
    return errors


def find_circular_dependencies(jobs: Dict[str, Dict]) -> List[List[str]]:
    """Find all circular dependencies in job configuration.
    
    Args:
        jobs: Dictionary mapping job IDs to job configs
        
    Returns:
        List of circular dependency paths
    """
    cycles = []
    visited = set()
    rec_stack = set()
    path = []
    
    def dfs(job_id: str) -> bool:
        visited.add(job_id)
        rec_stack.add(job_id)
        path.append(job_id)
        
        job = jobs.get(job_id, {})
        deps = job.get('dependencies', [])
        
        for dep in deps:
            if not isinstance(dep, str):
                continue
                
            if dep not in visited:
                if dep in jobs and dfs(dep):
                    return True
            elif dep in rec_stack:
                # Found a cycle
                cycle_start = path.index(dep)
                cycles.append(path[cycle_start:])
                return True
        
        path.pop()
        rec_stack.remove(job_id)
        return False
    
    # Check all jobs
    for job_id in jobs:
        if job_id not in visited:
            dfs(job_id)
    
    return cycles


def validate_job_dependencies(config: Dict[str, Any], logger) -> Tuple[bool, List[str]]:
    """Validate job dependencies for missing refs and circular dependencies.
    
    Args:
        config: Configuration dictionary
        logger: Logger instance
        
    Returns:
        Tuple of (is_valid, error_messages)
    """
    errors = []
    jobs = {job['id']: job for job in config['jobs'] 
            if isinstance(job, dict) and 'id' in job}
    
    # Check for missing dependencies
    for job_id, job in jobs.items():
        if 'dependencies' in job and isinstance(job['dependencies'], list):
            for dep in job['dependencies']:
                if isinstance(dep, str) and dep not in jobs:
                    errors.append(f"Job '{job_id}' depends on non-existent job '{dep}'")
    
    # Check for circular dependencies
    cycles = find_circular_dependencies(jobs)
    if cycles:
        for cycle in cycles:
            cycle_str = ' -> '.join(cycle) + f' -> {cycle[0]}'
            errors.append(f"Circular dependency detected: {cycle_str}")
    
    return len(errors) == 0, errors