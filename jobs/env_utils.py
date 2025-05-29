import re
import os

# Default environment variables to inherit from shell
DEFAULT_INHERIT_ENV = [
    # Essential system paths
    "PATH",
    "LD_LIBRARY_PATH",
    
    # User and system info
    "HOME",
    "USER",
    "SHELL",
    "HOSTNAME",
    
    # Terminal and display
    "TERM",
    "DISPLAY",
    
    # Locale settings
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    
    # Timezone
    "TZ",
    
    # Temporary directories
    "TMPDIR",
    "TEMP",
    "TMP",
    
    # Common tool paths (but not credentials)
    "JAVA_HOME",
    "PYTHON_HOME",
    "NODE_PATH"
]

def parse_env_vars(env_list, debug=False):
    """Parse KEY=value environment variables. Supports both repeated and comma-separated formats."""
    if debug:
        print(f"DEBUG: parse_env_vars input env_list = {env_list}")
    if not env_list:
        return {}
    env_dict = {}
    for env_entry in env_list:
        # Support comma-separated pairs in a single argument
        pairs = [p.strip() for p in env_entry.split(',') if p.strip()]
        for env_var in pairs:
            try:
                key, value = env_var.split('=', 1)
                if not key or not value:
                    raise ValueError
                env_dict[key] = value
            except ValueError:
                print(f"Warning: Skipping invalid environment variable: {env_var}")
    if debug:
        print(f"DEBUG: parse_env_vars output env_dict = {env_dict}")
    return env_dict

def substitute_env_vars_in_obj(obj, env_vars, _seen=None, logger=None):
    """
    Recursively substitute ${VAR} in strings within obj using env_vars dict.
    Handles circular references by tracking seen variables.
    """
    if _seen is None:
        _seen = set()
    
    pattern = re.compile(r'\${([A-Za-z_][A-Za-z0-9_]*)}')
    
    if isinstance(obj, dict):
        return {k: substitute_env_vars_in_obj(v, env_vars, _seen, logger) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_env_vars_in_obj(item, env_vars, _seen, logger) for item in obj]
    elif isinstance(obj, str):
        def replacer(match):
            var = match.group(1)
            if var in _seen:
                if logger:
                    logger.warning(f"Circular reference detected for variable: {var}")
                else:
                    print(f"Warning: Circular reference detected for variable: {var}")
                return match.group(0)  # Leave as-is to avoid infinite loop
            
            if var in env_vars:
                _seen.add(var)
                # Recursively substitute in the replacement value
                value = str(env_vars[var])
                result = pattern.sub(replacer, value)
                _seen.remove(var)
                return result
            else:
                if logger:
                    logger.debug(f"No value found for variable: {var}")
                return match.group(0)  # Leave as-is
        return pattern.sub(replacer, obj)
    else:
        return obj

def merge_env_vars(app_env, job_env):
    """
    Merge application-level and job-level environment variables.
    Job-level variables take precedence. All values are converted to strings.
    """
    merged = {k: str(v) for k, v in (app_env or {}).items()}
    for k, v in (job_env or {}).items():
        merged[k] = str(v)
    return merged

def interpolate_env_vars(env_vars, logger=None):
    """
    Interpolate environment variables that reference other variables.
    Returns a new dict with all ${VAR} references resolved.
    """
    if not env_vars:
        return {}
    
    # Create a copy to avoid modifying the original
    result = dict(env_vars)
    
    # Keep iterating until no more substitutions are made
    max_iterations = len(env_vars) + 1  # Prevent infinite loops
    for iteration in range(max_iterations):
        changed = False
        for key, value in result.items():
            if isinstance(value, str) and '${' in value:
                new_value = substitute_env_vars_in_obj(value, result, logger=logger)
                if new_value != value:
                    result[key] = new_value
                    changed = True
        
        if not changed:
            break
    else:
        if logger:
            logger.warning("Maximum iterations reached during environment variable interpolation")
    
    return result

def validate_env_vars(env_vars, logger=None):
    """
    Validate environment variable names and values.
    Returns (is_valid, error_messages)
    """
    import re
    errors = []
    
    # Reserved environment variable names that shouldn't be overridden
    RESERVED_VARS = {
        'PATH', 'HOME', 'USER', 'SHELL', 'PWD', 'OLDPWD', 
        'TERM', 'DISPLAY', 'LANG', 'LC_ALL', 'TZ',
        'LD_LIBRARY_PATH', 'PYTHONPATH', 'JAVA_HOME'
    }
    
    # Pattern for valid environment variable names
    # Must start with letter or underscore, followed by letters, numbers, or underscores
    VAR_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
    
    if not isinstance(env_vars, dict):
        errors.append("Environment variables must be a dictionary")
        return False, errors
    
    for key, value in env_vars.items():
        # Check variable name format
        if not VAR_NAME_PATTERN.match(key):
            errors.append(f"Invalid environment variable name: '{key}' (must match [A-Za-z_][A-Za-z0-9_]*)")
        
        # Warn about reserved variables
        if key in RESERVED_VARS:
            if logger:
                logger.warning(f"Overriding reserved environment variable: '{key}'")
        
        # Check for empty variable names
        if not key:
            errors.append("Empty environment variable name")
        
        # Convert value to string and check for issues
        str_value = str(value)
        
        # Check for null bytes (security issue)
        if '\0' in str_value:
            errors.append(f"Environment variable '{key}' contains null byte")
        
        # Warn about very long values
        if len(str_value) > 32768:  # 32KB limit
            errors.append(f"Environment variable '{key}' value exceeds 32KB")
    
    return len(errors) == 0, errors

def filter_shell_env(inherit_shell_env, logger=None):
    """
    Filter shell environment variables based on inherit_shell_env setting.
    
    Args:
        inherit_shell_env: Can be:
            - True: inherit all environment variables
            - False: inherit no environment variables
            - "default": use DEFAULT_INHERIT_ENV list
            - list: inherit only specified variables
        logger: Optional logger for debugging
    
    Returns:
        dict: Filtered environment variables
    """
    if inherit_shell_env is True:
        # Inherit all environment variables
        if logger:
            logger.debug("Inheriting all shell environment variables")
        return dict(os.environ)
    
    elif inherit_shell_env is False:
        # Don't inherit any environment variables
        if logger:
            logger.debug("Not inheriting any shell environment variables")
        return {}
    
    elif inherit_shell_env == "default":
        # Use default whitelist
        if logger:
            logger.debug(f"Inheriting default shell environment variables: {DEFAULT_INHERIT_ENV}")
        return {k: v for k, v in os.environ.items() if k in DEFAULT_INHERIT_ENV}
    
    elif isinstance(inherit_shell_env, list):
        # Use custom whitelist
        if logger:
            logger.debug(f"Inheriting specified shell environment variables: {inherit_shell_env}")
        return {k: v for k, v in os.environ.items() if k in inherit_shell_env}
    
    else:
        # Invalid type, log error and default to "default" behavior
        if logger:
            logger.warning(f"Invalid inherit_shell_env value: {inherit_shell_env}. Using default.")
        return {k: v for k, v in os.environ.items() if k in DEFAULT_INHERIT_ENV} 