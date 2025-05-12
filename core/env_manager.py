"""
env_manager.py - Environment variable management for Executioner.
"""

import re

class EnvManager:
    """
    Handles parsing, merging, and substitution of environment variables for jobs and the application.
    """
    def __init__(self, app_env=None):
        self.app_env = app_env or {}

    def parse_env_list(self, env_list, debug=False):
        """Parse a list of KEY=VALUE env strings into a dict."""
        if debug:
            print(f"DEBUG: parse_env_list input env_list = {env_list}")
        if not env_list:
            return {}
        env_dict = {}
        for env_entry in env_list:
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
            print(f"DEBUG: parse_env_list output env_dict = {env_dict}")
        return env_dict

    def merge_envs(self, *env_dicts):
        """Merge multiple env dicts with correct precedence (last wins)."""
        merged = {}
        for d in env_dicts:
            if d:
                merged.update(d)
        return merged

    def substitute_env_vars(self, obj, env_vars):
        """Recursively substitute ${VAR} in strings within obj using env_vars dict."""
        pattern = re.compile(r'\${([A-Za-z_][A-Za-z0-9_]*)}')
        if isinstance(obj, dict):
            return {k: self.substitute_env_vars(v, env_vars) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.substitute_env_vars(item, env_vars) for item in obj]
        elif isinstance(obj, str):
            def replacer(match):
                var = match.group(1)
                if var in env_vars:
                    return env_vars[var]
                else:
                    print(f"Warning: No value found for variable: {var}")
                    return match.group(0)
            return pattern.sub(replacer, obj)
        else:
            return obj 