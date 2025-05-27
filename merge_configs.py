#!/usr/bin/env python3
"""
Merge multiple executioner configuration files into a single config.

This script takes a comma-separated list of executioner config files and merges them
into a single configuration. The last job of each config becomes a dependency for
the first job in the next config, creating a sequential workflow.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Set


def load_config(file_path: str) -> Dict[str, Any]:
    """Load and parse a JSON configuration file."""
    try:
        # Convert to Path object and resolve
        path = Path(file_path).resolve()
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Configuration file '{file_path}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in '{file_path}': {e}", file=sys.stderr)
        sys.exit(1)


def find_last_jobs(jobs: List[Dict[str, Any]]) -> List[str]:
    """Find jobs that are not dependencies for any other job (terminal jobs)."""
    all_job_ids = {job['id'] for job in jobs}
    jobs_with_dependents = set()
    
    for job in jobs:
        if 'dependencies' in job:
            jobs_with_dependents.update(job['dependencies'])
    
    terminal_jobs = all_job_ids - jobs_with_dependents
    return list(terminal_jobs)


def prefix_job_ids(jobs: List[Dict[str, Any]], prefix: str) -> List[Dict[str, Any]]:
    """Add a prefix to all job IDs and update dependencies accordingly."""
    prefixed_jobs = []
    
    for job in jobs:
        new_job = job.copy()
        new_job['id'] = f"{prefix}_{job['id']}"
        
        if 'dependencies' in job:
            new_job['dependencies'] = [f"{prefix}_{dep}" for dep in job['dependencies']]
        
        prefixed_jobs.append(new_job)
    
    return prefixed_jobs


def detect_job_id_conflicts(configs_with_jobs: List[tuple]) -> Dict[str, List[str]]:
    """Detect job ID conflicts across configurations.
    
    Returns a dict mapping job IDs to list of config files that contain them.
    """
    job_id_to_configs = {}
    
    for config_file, jobs in configs_with_jobs:
        for job in jobs:
            job_id = job['id']
            if job_id not in job_id_to_configs:
                job_id_to_configs[job_id] = []
            job_id_to_configs[job_id].append(config_file)
    
    # Return only job IDs that appear in multiple configs
    conflicts = {job_id: configs for job_id, configs in job_id_to_configs.items() 
                 if len(configs) > 1}
    
    return conflicts


def merge_configs(config_files: List[str], app_name: str, prefix_mode: str = 'on_conflict') -> Dict[str, Any]:
    """Merge multiple config files into a single configuration.
    
    Args:
        config_files: List of config file paths
        app_name: Application name for merged config
        prefix_mode: How to handle job ID prefixing:
            - 'always': Always prefix job IDs with filename
            - 'on_conflict': Only prefix when conflicts detected (default)
            - 'never': Never prefix, fail on conflicts
    """
    if not config_files:
        print("Error: No configuration files provided.", file=sys.stderr)
        sys.exit(1)
    
    # Load all configs first
    configs_with_jobs = []
    for config_file in config_files:
        config = load_config(config_file)
        configs_with_jobs.append((config_file, config.get('jobs', [])))
    
    # Detect conflicts if needed
    conflicts = {}
    if prefix_mode in ['on_conflict', 'never']:
        conflicts = detect_job_id_conflicts(configs_with_jobs)
        
        if conflicts and prefix_mode == 'never':
            print("Error: Job ID conflicts detected. Cannot merge without prefixing.", file=sys.stderr)
            print("Conflicts found:", file=sys.stderr)
            for job_id, files in conflicts.items():
                print(f"  - Job ID '{job_id}' appears in: {', '.join(files)}", file=sys.stderr)
            sys.exit(1)
    
    merged_config = {
        "application_name": app_name,
        "jobs": []
    }
    
    # Track global settings that should be merged
    email_addresses = set()
    env_variables = {}
    email_on_success = False
    email_on_failure = False
    parallel = False
    max_workers = None
    
    previous_last_jobs = []
    
    for idx, (config_file, _) in enumerate(configs_with_jobs):
        config = load_config(config_file)
        
        # Extract file name without extension for prefixing
        file_prefix = Path(config_file).stem
        
        jobs = config.get('jobs', [])
        
        # Determine if we should prefix this config's jobs
        should_prefix = False
        if prefix_mode == 'always':
            should_prefix = True
        elif prefix_mode == 'on_conflict' and conflicts:
            # Check if any job in this config has conflicts
            for job in jobs:
                if job['id'] in conflicts:
                    should_prefix = True
                    break
        
        # Apply prefixing if needed
        if should_prefix:
            jobs = prefix_job_ids(jobs, file_prefix)
        
        # Add dependency from previous config's last jobs to this config's first jobs
        if previous_last_jobs and jobs:
            # Find jobs with no dependencies (entry points)
            entry_jobs = [job for job in jobs if 'dependencies' not in job or not job['dependencies']]
            
            # If no entry jobs, use all jobs as potential entry points
            if not entry_jobs:
                entry_jobs = jobs
            
            # Add dependencies to entry jobs
            for job in entry_jobs:
                if 'dependencies' not in job:
                    job['dependencies'] = []
                job['dependencies'].extend(previous_last_jobs)
        
        # Find the last jobs in this config for the next iteration
        previous_last_jobs = find_last_jobs(jobs)
        
        # Add jobs to merged config
        merged_config['jobs'].extend(jobs)
        
        # Merge global settings
        if 'email_address' in config:
            email_addresses.add(config['email_address'])
        
        if 'env_variables' in config:
            env_variables.update(config['env_variables'])
        
        email_on_success = email_on_success or config.get('email_on_success', False)
        email_on_failure = email_on_failure or config.get('email_on_failure', False)
        parallel = parallel or config.get('parallel', False)
        
        if 'max_workers' in config:
            max_workers = max(max_workers or 0, config['max_workers'])
    
    # Create final config with proper ordering (jobs last)
    final_config = {
        "application_name": app_name
    }
    
    # Add merged global settings first
    if email_addresses:
        final_config['email_address'] = ', '.join(email_addresses)
    
    if email_on_success:
        final_config['email_on_success'] = True
    
    if email_on_failure:
        final_config['email_on_failure'] = True
    
    if parallel:
        final_config['parallel'] = True
    
    if max_workers:
        final_config['max_workers'] = max_workers
    
    if env_variables:
        final_config['env_variables'] = env_variables
    
    # Add jobs last
    final_config['jobs'] = merged_config['jobs']
    
    return final_config


def main():
    parser = argparse.ArgumentParser(
        description='Merge multiple executioner configuration files into a single config.',
        epilog='''Examples:
  %(prog)s config1.json,config2.json -a "MergedWorkflow" -o merged.json
  %(prog)s config1.json,config2.json -a "MergedWorkflow" --prefix-job-ids
  %(prog)s config1.json,config2.json -a "MergedWorkflow" --no-prefix
  
Default behavior: Automatically detects job ID conflicts and only prefixes when necessary.''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        'configs',
        help='Comma-separated list of configuration files to merge (e.g., "file1.json,file2.json")'
    )
    
    parser.add_argument(
        '-a', '--app-name',
        required=True,
        help='Application name for the merged configuration'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='merged_config.json',
        help='Output file name (default: merged_config.json)'
    )
    
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Output compact JSON without indentation (default: pretty-printed with indentation)'
    )
    
    # Add mutually exclusive group for prefix options
    prefix_group = parser.add_mutually_exclusive_group()
    prefix_group.add_argument(
        '--prefix-job-ids',
        action='store_const',
        dest='prefix_mode',
        const='always',
        help='Always prefix job IDs with config filename'
    )
    prefix_group.add_argument(
        '--prefix-on-conflict',
        action='store_const',
        dest='prefix_mode',
        const='on_conflict',
        help='Only prefix job IDs when conflicts are detected (default)'
    )
    prefix_group.add_argument(
        '--no-prefix',
        action='store_const',
        dest='prefix_mode',
        const='never',
        help='Never prefix job IDs, fail if conflicts are detected'
    )
    
    # Set default prefix mode
    parser.set_defaults(prefix_mode='on_conflict')
    
    args = parser.parse_args()
    
    # Parse comma-separated config files
    config_files = [f.strip() for f in args.configs.split(',') if f.strip()]
    
    # Merge configurations
    merged_config = merge_configs(config_files, args.app_name, args.prefix_mode)
    
    # Write output
    try:
        with open(args.output, 'w') as f:
            if args.compact:
                json.dump(merged_config, f)
            else:
                json.dump(merged_config, f, indent=2)
                f.write('\n')
        
        print(f"Successfully merged {len(config_files)} configuration files into '{args.output}'")
        print(f"Total jobs in merged config: {len(merged_config['jobs'])}")
        
    except IOError as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()