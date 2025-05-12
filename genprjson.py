#!/usr/bin/env python3
#!/usr/bin/env agspython3
import sys
import json
import re

def parse_prhelper(lines):
    jobs = []
    sql_cmd_pattern = re.compile(r"sqlplus /nolog @(PR_\d+\.sql) .*")
    for line in lines:
        match = sql_cmd_pattern.search(line)
        if match:
            sql_file = match.group(1)
            job_id = sql_file.replace('.sql', '')
            command = line.strip()
            log_file = f"./logs/{job_id}.log"
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
    return jobs

def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            lines = f.readlines()
    else:
        lines = sys.stdin.readlines()

    jobs = parse_prhelper(lines)
    # Insert a critical job at the beginning if 'CRITICAL' is found
    if any('CRITICAL' in line for line in lines):
        critical_job = {
            "id": "critical_check",
            "description": "Critical issue detected in input. This job always fails.",
            "command": "false # Simulated critical failure",
            "post_checks": [],
            "dependencies": []
        }
        jobs.insert(0, critical_job)
    # Add dependencies
    for i, job in enumerate(jobs):
        if i == 0:
            job["dependencies"] = []
        else:
            job["dependencies"] = [jobs[i-1]["id"]]
    config = {
        "application_name": "data_pipeline",
        "jobs": jobs
    }
    print(json.dumps(config, indent=2))

if __name__ == "__main__":
    main() 
