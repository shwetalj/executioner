#!/usr/bin/env python3
"""
Generate executioner configuration from PR helper files.

This script parses input files containing SQL commands and other operations,
converting them into executioner JSON configuration format. It automatically:
- Extracts SQL commands and creates jobs with Oracle error checking
- Handles 'run -u' commands as separate jobs
- Creates sequential dependencies between jobs
- Optionally inserts a critical failure job if CRITICAL keyword is found
"""

import sys
import json
import re
import argparse
from pathlib import Path


def parse_prhelper(lines, log_dir, check_critical=True):
    """Parse input lines and generate job configurations.
    
    Args:
        lines: List of input lines to parse
        log_dir: Directory where log files will be written
        check_critical: Whether to check for CRITICAL keyword
        
    Returns:
        List of job dictionaries
    """
    jobs = []
    sql_cmd_pattern = re.compile(r"sqlplus /nolog @(PR_(\d+)\.sql) .*")
    
    # Parse SQL commands
    for line in lines:
        match = sql_cmd_pattern.search(line)
        if match:
            sql_file = match.group(1)
            pr_number = match.group(2)
            job_id = sql_file.replace('.sql', '')
            command = line.strip()
            log_file = f"{log_dir}*{pr_number}*.log"
            job = {
                "id": job_id,
                "description": f"Running {sql_file}",
                "command": command,
                "post_checks": [
                    {
                        "name": "check_no_ora_errors",
                        "params": {
                            "log_file": log_file
                        }
                    }
                ]
            }
            jobs.append(job)
    
    # Find and append 'run -u' commands as jobs
    run_cmd_count = 1
    for line in lines:
        if line.strip().startswith('run -u'):
            job_id = f"run_cmd_{run_cmd_count}"
            command = line.strip()
            job = {
                "id": job_id,
                "description": f"Run command: {command}",
                "command": command
            }
            jobs.append(job)
            run_cmd_count += 1
    
    # Insert a critical job at the beginning if 'CRITICAL' is found
    if check_critical and any('CRITICAL' in line for line in lines):
        critical_job = {
            "id": "critical_check",
            "description": "Critical issue detected in input. This job always fails.",
            "command": "false # Simulated critical failure",
            "post_checks": [],
            "dependencies": []
        }
        jobs.insert(0, critical_job)
    
    # Add sequential dependencies
    for i, job in enumerate(jobs):
        if i == 0:
            job["dependencies"] = []
        else:
            job["dependencies"] = [jobs[i-1]["id"]]
    
    return jobs


def extract_log_directory(lines, default_log_dir):
    """Extract log directory from input lines.
    
    Args:
        lines: List of input lines
        default_log_dir: Default directory to use if not found
        
    Returns:
        Log directory path
    """
    for line in lines:
        if line.strip().startswith('Log Directory:'):
            log_dir = line.split(':', 1)[1].strip()
            if not log_dir.endswith('/'):
                log_dir += '/'
            return log_dir
    return default_log_dir


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  # Read from file and output to stdout
  %(prog)s input.txt
  
  # Read from stdin and save to file
  cat commands.txt | %(prog)s -o config.json
  
  # Customize application name and log directory
  %(prog)s input.txt -a "MyPipeline" -l "/var/log/pipeline/"
  
  # Disable critical check
  %(prog)s input.txt --no-critical-check
"""
    )
    
    parser.add_argument(
        'input_file',
        nargs='?',
        help='Input file containing commands (default: read from stdin)'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output file for JSON configuration (default: stdout)'
    )
    
    parser.add_argument(
        '-a', '--app-name',
        default='data_pipeline',
        help='Application name for the configuration (default: data_pipeline)'
    )
    
    parser.add_argument(
        '-l', '--log-dir',
        default='./logs/',
        help='Default log directory (default: ./logs/)'
    )
    
    parser.add_argument(
        '--no-critical-check',
        action='store_true',
        help='Disable automatic critical failure job insertion'
    )
    
    parser.add_argument(
        '--pretty',
        action='store_true',
        default=True,
        help='Pretty-print JSON output (default: enabled)'
    )
    
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Output compact JSON without indentation'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose output to stderr'
    )
    
    args = parser.parse_args()
    
    # Read input
    try:
        if args.input_file:
            if args.verbose:
                print(f"Reading from file: {args.input_file}", file=sys.stderr)
            with open(args.input_file, 'r') as f:
                lines = f.readlines()
        else:
            if args.verbose:
                print("Reading from stdin...", file=sys.stderr)
            lines = sys.stdin.readlines()
            if not lines:
                print("Error: No input provided. Use -h for help.", file=sys.stderr)
                sys.exit(1)
    except FileNotFoundError:
        print(f"Error: Input file '{args.input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Process log directory
    log_dir = extract_log_directory(lines, args.log_dir)
    if args.verbose:
        print(f"Using log directory: {log_dir}", file=sys.stderr)
    
    # Parse and generate jobs
    jobs = parse_prhelper(lines, log_dir, check_critical=not args.no_critical_check)
    
    if not jobs:
        print("Warning: No jobs found in input.", file=sys.stderr)
    elif args.verbose:
        print(f"Generated {len(jobs)} jobs", file=sys.stderr)
    
    # Create configuration
    config = {
        "application_name": args.app_name,
        "jobs": jobs
    }
    
    # Output JSON
    try:
        json_output = json.dumps(config, indent=2 if not args.compact else None)
        if not args.compact:
            json_output += '\n'
        
        if args.output:
            with open(args.output, 'w') as f:
                f.write(json_output)
            if args.verbose:
                print(f"Configuration written to: {args.output}", file=sys.stderr)
        else:
            print(json_output, end='')
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()