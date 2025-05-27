import re

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

def substitute_env_vars_in_obj(obj, env_vars):
    """
    Recursively substitute ${VAR} in strings within obj using env_vars dict.
    """
    pattern = re.compile(r'\${([A-Za-z_][A-Za-z0-9_]*)}')
    if isinstance(obj, dict):
        return {k: substitute_env_vars_in_obj(v, env_vars) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [substitute_env_vars_in_obj(item, env_vars) for item in obj]
    elif isinstance(obj, str):
        def replacer(match):
            var = match.group(1)
            if var in env_vars:
                return env_vars[var]
            else:
                print(f"Warning: No value found for variable: {var}")
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

def validate_env_vars(env_vars):
    """
    Placeholder for environment variable validation logic.
    """
    # Example: check for reserved keys, invalid names, etc.
    return True 