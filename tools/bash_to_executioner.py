#!/usr/bin/env python3

import argparse
import json
import re
import sys
from typing import Dict, List, Tuple, Optional

def parse_environment_variables(lines: List[str], start_index: int = 0) -> Tuple[Dict[str, str], int]:
    """
    Parse environment variable declarations from bash script lines.
    Returns a dict of env vars and the index where parsing stopped.
    """
    env_vars = {}
    i = start_index
    
    # Pattern to match export statements
    export_pattern = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
    
    # Only parse top-level env vars when start_index points to beginning
    if start_index <= 1:  # 0 or 1 (after shebang)
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines and comments at the top
            if not line or line.startswith('#'):
                i += 1
                continue
                
            # Check for export statement
            export_match = export_pattern.match(line)
            if export_match:
                var_name = export_match.group(1)
                var_value = export_match.group(2).strip()
                # Remove quotes if present
                if (var_value.startswith('"') and var_value.endswith('"')) or \
                   (var_value.startswith("'") and var_value.endswith("'")):
                    var_value = var_value[1:-1]
                env_vars[var_name] = var_value
                i += 1
                continue
                
            # If we hit a non-env var line, stop parsing
            break
    
    return env_vars, i

def is_trivial_command(command: str) -> bool:
    """
    Check if a command is trivial (like echo, printf, comment) and should be grouped.
    """
    cmd = command.strip()
    trivial_commands = ['echo', 'printf', 'print', 'comment', '#']
    
    # Check if command starts with any trivial command
    for trivial in trivial_commands:
        if cmd.startswith(trivial + ' ') or cmd.startswith(trivial + '\t'):
            return True
    
    # Also consider empty lines and comments as trivial
    if not cmd or cmd.startswith('#'):
        return True
        
    return False

def parse_bash_commands(lines: List[str], start_index: int) -> List[Dict]:
    """
    Parse bash script lines into individual commands/jobs.
    Returns a list of job dictionaries.
    """
    jobs = []
    current_job_commands = []
    job_env_vars = {}
    job_counter = 1
    
    # Patterns
    export_pattern = re.compile(r'^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)=(.*)$')
    
    i = start_index
    while i < len(lines):
        line = lines[i]
        stripped_line = line.strip()
        
        # Skip empty lines in between commands
        if not stripped_line:
            if current_job_commands:
                current_job_commands.append(line)
            i += 1
            continue
        
        # Check for export statement (job-level env var)
        export_match = export_pattern.match(stripped_line)
        if export_match:
            var_name = export_match.group(1)
            var_value = export_match.group(2).strip()
            # Remove quotes if present
            if (var_value.startswith('"') and var_value.endswith('"')) or \
               (var_value.startswith("'") and var_value.endswith("'")):
                var_value = var_value[1:-1]
            job_env_vars[var_name] = var_value
            i += 1
            continue
        
        # Handle multi-line constructs (loops, conditionals)
        if stripped_line.startswith(('for ', 'while ', 'if ', 'case ')):
            # Find the matching done/fi/esac
            block_lines = [line]
            i += 1
            
            # Determine what we're looking for
            if stripped_line.startswith(('for ', 'while ')):
                end_pattern = r'^\s*done\s*$'
            elif stripped_line.startswith('if '):
                end_pattern = r'^\s*fi\s*$'
            elif stripped_line.startswith('case '):
                end_pattern = r'^\s*esac\s*$'
            
            # Collect all lines until we find the end
            while i < len(lines):
                block_lines.append(lines[i])
                if re.match(end_pattern, lines[i].strip()):
                    break
                i += 1
            
            # Create a job for this block
            job_id = f"job_{job_counter}"
            job = {
                "id": job_id,
                "description": f"Execute {stripped_line.split()[0]} block",
                "command": '\n'.join(block_lines)
            }
            
            # Add env vars if any were collected
            if job_env_vars:
                job["env_variables"] = job_env_vars.copy()
                job_env_vars.clear()
            
            # Add dependency on previous job
            if job_counter > 1:
                job["dependencies"] = [f"job_{job_counter - 1}"]
            
            jobs.append(job)
            job_counter += 1
            i += 1
            continue
        
        # Check if this is a trivial command
        if is_trivial_command(stripped_line):
            current_job_commands.append(line)
        else:
            # If we have accumulated trivial commands, create a job for them first
            if current_job_commands:
                job_id = f"job_{job_counter}"
                job = {
                    "id": job_id,
                    "description": "Execute script output/logging commands",
                    "command": '\n'.join(current_job_commands).strip()
                }
                
                # Add dependency on previous job
                if job_counter > 1:
                    job["dependencies"] = [f"job_{job_counter - 1}"]
                
                jobs.append(job)
                job_counter += 1
                current_job_commands = []
            
            # Create a job for this non-trivial command
            job_id = f"job_{job_counter}"
            
            # Generate a description based on the command
            cmd_parts = stripped_line.split()
            if cmd_parts:
                description = f"Execute {cmd_parts[0]} command"
            else:
                description = "Execute command"
            
            job = {
                "id": job_id,
                "description": description,
                "command": stripped_line
            }
            
            # Add env vars if any were collected
            if job_env_vars:
                job["env_variables"] = job_env_vars.copy()
                job_env_vars.clear()
            
            # Add dependency on previous job
            if job_counter > 1:
                job["dependencies"] = [f"job_{job_counter - 1}"]
            
            jobs.append(job)
            job_counter += 1
        
        i += 1
    
    # Don't forget any remaining trivial commands
    if current_job_commands:
        job_id = f"job_{job_counter}"
        job = {
            "id": job_id,
            "description": "Execute script output/logging commands",
            "command": '\n'.join(current_job_commands).strip()
        }
        
        # Add dependency on previous job
        if job_counter > 1:
            job["dependencies"] = [f"job_{job_counter - 1}"]
        
        jobs.append(job)
    
    return jobs

def create_executioner_config(script_content: str, app_name: str = "bash_script") -> Dict:
    """
    Convert a bash script to executioner config format.
    """
    lines = script_content.split('\n')
    
    # Skip shebang if present
    start_index = 0
    if lines and lines[0].strip().startswith('#!'):
        start_index = 1
    
    # Parse application-level environment variables (at the top)
    app_env_vars, content_start = parse_environment_variables(lines, start_index)
    
    # Parse the rest of the script into jobs
    jobs = parse_bash_commands(lines, content_start)
    
    # Create the config structure
    config = {
        "application_name": app_name,
        "jobs": jobs
    }
    
    # Add application-level environment variables if any
    if app_env_vars:
        config["env_variables"] = app_env_vars
    
    # If there's only one job, don't include dependencies
    if len(jobs) == 1 and "dependencies" in jobs[0]:
        del jobs[0]["dependencies"]
    
    return config

def main():
    parser = argparse.ArgumentParser(
        description="Convert bash scripts to executioner config format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert from stdin
  cat script.sh | %(prog)s -o config.json

  # Convert from file
  %(prog)s -i script.sh -o config.json

  # Specify application name
  %(prog)s -i script.sh -o config.json --app-name "my_workflow"

Notes:
  - Environment variables at the top of the script become application-level env_variables
  - Environment variables elsewhere in the script become job-level env_variables
  - Each non-trivial command becomes a separate job with dependencies
  - Trivial commands (echo, printf, etc.) are grouped together
  - Multi-line constructs (loops, conditionals) are kept as single jobs
        """
    )
    
    parser.add_argument('-i', '--input', type=str, help='Input bash script file (default: stdin)')
    parser.add_argument('-o', '--output', type=str, required=True, help='Output executioner config file')
    parser.add_argument('--app-name', type=str, default='bash_script', help='Application name for the config (default: bash_script)')
    
    args = parser.parse_args()
    
    # Read input script
    if args.input:
        try:
            with open(args.input, 'r') as f:
                script_content = f.read()
        except FileNotFoundError:
            print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Read from stdin
        try:
            script_content = sys.stdin.read()
        except KeyboardInterrupt:
            print("\nOperation cancelled", file=sys.stderr)
            sys.exit(1)
    
    if not script_content.strip():
        print("Error: Empty input script", file=sys.stderr)
        sys.exit(1)
    
    # Convert to executioner config
    config = create_executioner_config(script_content, args.app_name)
    
    # Write output
    try:
        with open(args.output, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Successfully converted bash script to executioner config: {args.output}")
    except Exception as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()