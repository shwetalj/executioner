#!/usr/bin/env python3
import argparse
import sqlite3
import re
import sys
import json
import datetime
import pytz
from tabulate import tabulate

# Constants
DB_FILE = "jobs_history.db"
EASTERN_TZ = pytz.timezone('US/Eastern')

# ANSI Color Codes
COLOR_BLUE = "\033[94m"      # Blue for Job ID
COLOR_GREEN = "\033[32m"     # Green for Success
COLOR_RED = "\033[91m"       # Red for Failures
COLOR_YELLOW = "\033[33m"    # Yellow for headers
COLOR_RESET = "\033[0m"      # Reset to default

# Function to calculate visible length excluding ANSI color codes
def visible_len(s):
    """Calculate the visible length of a string by removing ANSI color codes."""
    # Remove all ANSI escape sequences
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return len(ansi_escape.sub('', s))

def get_max_run_id(app_name=None):
    """Get the most recent run_id from the database, optionally filtered by application name."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        # Use CAST to ensure we get integer values
        if app_name:
            cursor.execute("SELECT MAX(CAST(run_id AS INTEGER)) FROM job_history WHERE application_name = ?", (app_name,))
        else:
            cursor.execute("SELECT MAX(CAST(run_id AS INTEGER)) FROM job_history")
        max_run_id = cursor.fetchone()[0]
        result = int(max_run_id) if max_run_id is not None else 0
    except (sqlite3.Error, ValueError, TypeError):
        # Fallback if there's an issue with the database or type conversion
        print("Warning: Could not determine last run_id properly from database. Defaulting to 0.")
        result = 0
    conn.close()
    return result

def get_run_data(run_id, pattern=None, app_name=None):
    """Get data for a specific run_id with optional regex filtering and app name filtering."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        query = """
        SELECT id, description, command, status, application_name, last_run
        FROM job_history
        WHERE run_id = ?
        """
        
        params = [run_id]
        
        # Add application name filter if provided
        if app_name:
            query += " AND application_name = ?"
            params.append(app_name)
        
        query += " ORDER BY last_run"
        
        cursor.execute(query, tuple(params))
        runs = cursor.fetchall()
        
        # Apply regex pattern if provided
        if pattern:
            regex = re.compile(pattern, re.IGNORECASE)
            filtered_runs = [run for run in runs if (
                regex.search(str(run[0])) or  # job id
                regex.search(str(run[1])) or  # description
                regex.search(str(run[2])) or  # command
                regex.search(str(run[3])) or  # status
                regex.search(str(run[4]))     # application_name
            )]
            runs = filtered_runs
    except (sqlite3.Error, ValueError, TypeError) as e:
        print(f"Warning: Error retrieving run data: {e}")
        runs = []
    
    conn.close()
    return runs

def get_all_runs(app_name=None):
    """Get a summary of all runs with optional application name filter."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Get all unique run_ids, optionally filtered by application_name
    try:
        query = "SELECT DISTINCT CAST(run_id AS INTEGER) as run_id FROM job_history"
        params = []
        
        if app_name:
            query += " WHERE application_name = ?"
            params.append(app_name)
        
        query += " ORDER BY run_id"
        
        cursor.execute(query, tuple(params))
        run_ids = [row[0] for row in cursor.fetchall()]
        
        # For each run_id, get success/failure stats
        run_stats = []
        for run_id in run_ids:
            base_query = """
                SELECT 
                    CAST(run_id AS INTEGER) as run_id,
                    MIN(last_run) as start_time,
                    MAX(last_run) as end_time,
                    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_count,
                    SUM(CASE WHEN status = 'TIMEOUT' THEN 1 ELSE 0 END) as timeout_count,
                    COUNT(*) as total_jobs,
                    application_name
                FROM job_history
                WHERE run_id = ?
            """
            
            query_params = [run_id]
            
            if app_name:
                base_query += " AND application_name = ?"
                query_params.append(app_name)
            
            base_query += " GROUP BY application_name"
            
            cursor.execute(base_query, tuple(query_params))
            run_stats.extend(cursor.fetchall())
    except (sqlite3.Error, ValueError, TypeError) as e:
        print(f"Warning: Error retrieving run stats: {e}")
        run_stats = []
    
    conn.close()
    return run_stats

def convert_to_eastern(timestamp_str):
    """Convert UTC timestamp to Eastern Time."""
    try:
        dt_utc = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        dt_utc = pytz.UTC.localize(dt_utc)
        dt_eastern = dt_utc.astimezone(EASTERN_TZ)
        return dt_eastern.strftime("%Y-%m-%d %H:%M:%S %Z")
    except (ValueError, TypeError):
        return timestamp_str

def format_duration(start_time, end_time):
    """Calculate and format the duration between two timestamps."""
    try:
        # Strip timezone info if present for duration calculation
        start_clean = start_time.split(" ")[0] + " " + start_time.split(" ")[1]
        end_clean = end_time.split(" ")[0] + " " + end_time.split(" ")[1]
        
        start = datetime.datetime.strptime(start_clean, "%Y-%m-%d %H:%M:%S")
        end = datetime.datetime.strptime(end_clean, "%Y-%m-%d %H:%M:%S")
        delta = end - start
        seconds = delta.total_seconds()
        
        if seconds < 60:
            return f"{seconds:.2f}s"
        elif seconds < 3600:
            return f"{seconds/60:.2f}m"
        else:
            return f"{seconds/3600:.2f}h"
    except (ValueError, TypeError):
        return "N/A"

def print_run_details(run_data, run_id):
    """Print detailed information for a specific run."""
    if not run_data:
        print(f"No data found for run_id {run_id}")
        return

    # Calculate overall status
    failed_jobs = [job for job in run_data if job[3] == 'FAILED' or job[3] == 'TIMEOUT']
    overall_status = f"{COLOR_RED}FAILED{COLOR_RESET}" if failed_jobs else f"{COLOR_GREEN}SUCCESS{COLOR_RESET}"
    
    # Get start and end time and application name
    start_time = convert_to_eastern(run_data[0][5])
    end_time = convert_to_eastern(run_data[-1][5])
    application_name = run_data[0][4]
    duration = format_duration(start_time, end_time)
    
    # Create a header with tabulate
    header_title = f"{COLOR_YELLOW}RUN DETAILS: ID {run_id}{COLOR_RESET}"
    header_table = [[header_title]]
    print("\n" + tabulate(header_table, tablefmt="grid"))
    
    # Create a table layout for run info using tabulate
    info_data = [
        [f"{COLOR_BLUE}Application{COLOR_RESET}", application_name],
        [f"{COLOR_BLUE}Start Time{COLOR_RESET}", start_time],
        [f"{COLOR_BLUE}End Time{COLOR_RESET}", end_time],
        [f"{COLOR_BLUE}Duration{COLOR_RESET}", duration],
        [f"{COLOR_BLUE}Status{COLOR_RESET}", overall_status],
        [f"{COLOR_BLUE}Total Jobs{COLOR_RESET}", len(run_data)],
        [f"{COLOR_BLUE}Success Jobs{COLOR_RESET}", len([j for j in run_data if j[3] == 'SUCCESS'])],
        [f"{COLOR_BLUE}Failed Jobs{COLOR_RESET}", len([j for j in run_data if j[3] == 'FAILED' or j[3] == 'TIMEOUT'])]
    ]
    
    print(tabulate(info_data, tablefmt="grid"))
    
    # Print job details header using tabulate
    job_list_header = [[f"{COLOR_YELLOW}JOB LIST{COLOR_RESET}"]]
    print("\n" + tabulate(job_list_header, tablefmt="grid"))
    
    # Sort jobs by timestamp to show execution order
    sorted_jobs = sorted(run_data, key=lambda job: job[5])
    
    # Prepare table data
    table_data = []
    headers = [f"{COLOR_YELLOW}Job ID{COLOR_RESET}", 
               f"{COLOR_YELLOW}App{COLOR_RESET}", 
               f"{COLOR_YELLOW}Description{COLOR_RESET}", 
               f"{COLOR_YELLOW}Command{COLOR_RESET}", 
               f"{COLOR_YELLOW}Status{COLOR_RESET}", 
               f"{COLOR_YELLOW}Timestamp{COLOR_RESET}"]
    
    for job in sorted_jobs:
        job_id = job[0]
        description = job[1]  
        command = job[2]
        status = job[3]
        app_name = job[4]
        timestamp = convert_to_eastern(job[5])
        
        # Add color to status
        if status == "SUCCESS":
            status_colored = f"{COLOR_GREEN}{status}{COLOR_RESET}"
        elif status == "FAILED":
            status_colored = f"{COLOR_RED}{status}{COLOR_RESET}"
        elif status == "TIMEOUT":
            status_colored = f"{COLOR_YELLOW}{status}{COLOR_RESET}"
        else:
            status_colored = status
        
        job_id_colored = f"{COLOR_BLUE}{job_id}{COLOR_RESET}"
        
        table_data.append([job_id_colored, app_name, description, command, status_colored, timestamp])
    
    # Print the table using tabulate
    print(tabulate(table_data, headers=headers, tablefmt="grid"))

def print_all_runs(run_stats):
    """Print summary information for all runs."""
    if not run_stats:
        print("No runs found in the database")
        return
    
    # Create a header with tabulate
    header_title = f"{COLOR_YELLOW}ALL RUNS SUMMARY{COLOR_RESET}"
    header_table = [[header_title]]
    print("\n" + tabulate(header_table, tablefmt="grid"))
    
    # Group runs by application name
    app_runs = {}
    for stat in run_stats:
        run_id = stat[0]
        start_time = stat[1]
        end_time = stat[2]
        success_count = stat[3]
        failed_count = stat[4]
        timeout_count = stat[5]
        total_jobs = stat[6]
        application_name = stat[7] if len(stat) > 7 else "unknown"
        
        if application_name not in app_runs:
            app_runs[application_name] = []
        
        app_runs[application_name].append({
            "run_id": run_id,
            "start_time": start_time,
            "end_time": end_time,
            "success_count": success_count,
            "failed_count": failed_count,
            "timeout_count": timeout_count,
            "total_jobs": total_jobs
        })
    
    # We don't need column widths since we're using tabulate for all tables
    
    # Print for each application
    for app_name, runs in app_runs.items():
        # Application header using tabulate
        app_header = f"{COLOR_YELLOW}APPLICATION: {app_name}{COLOR_RESET}"
        app_header_table = [[app_header]]
        print("\n" + tabulate(app_header_table, tablefmt="grid"))
        
        # Prepare table headers with color
        headers = [
            f"{COLOR_YELLOW}Run ID{COLOR_RESET}", 
            f"{COLOR_YELLOW}Start Time{COLOR_RESET}",
            f"{COLOR_YELLOW}End Time{COLOR_RESET}", 
            f"{COLOR_YELLOW}Duration{COLOR_RESET}",
            f"{COLOR_YELLOW}Success{COLOR_RESET}", 
            f"{COLOR_YELLOW}Failed{COLOR_RESET}",
            f"{COLOR_YELLOW}Timeout{COLOR_RESET}", 
            f"{COLOR_YELLOW}Total{COLOR_RESET}",
            f"{COLOR_YELLOW}Status{COLOR_RESET}"
        ]
        
        # Prepare table data
        table_data = []
        
        # Sort runs by run_id in descending order (most recent first)
        for run in sorted(runs, key=lambda x: x["run_id"], reverse=True):
            run_id = run["run_id"]
            start_time = convert_to_eastern(run["start_time"])
            end_time = convert_to_eastern(run["end_time"])
            success_count = run["success_count"]
            failed_count = run["failed_count"]
            timeout_count = run["timeout_count"]
            total_jobs = run["total_jobs"]
            
            # Calculate overall status
            status = f"{COLOR_GREEN}SUCCESS{COLOR_RESET}" if failed_count == 0 and timeout_count == 0 else f"{COLOR_RED}FAILED{COLOR_RESET}"
            duration = format_duration(start_time, end_time)
            
            # Add color to run_id
            run_id_colored = f"{COLOR_BLUE}{run_id}{COLOR_RESET}"
            
            table_data.append([
                run_id_colored,
                start_time,
                end_time,
                duration,
                success_count,
                failed_count,
                timeout_count,
                total_jobs,
                status
            ])
        
        # Print the table using tabulate
        print(tabulate(table_data, headers=headers, tablefmt="grid"))

def export_json(run_data, run_id, output_file):
    """Export run data to a JSON file."""
    # Get application name from first job
    application_name = run_data[0][4] if run_data else "unknown"
    
    json_data = {
        "run_id": run_id,
        "application_name": application_name,
        "jobs": []
    }
    
    for job in run_data:
        json_data["jobs"].append({
            "id": job[0],
            "description": job[1],
            "command": job[2],
            "status": job[3],
            "application_name": job[4],
            "timestamp": convert_to_eastern(job[5])
        })
    
    with open(output_file, 'w') as f:
        json.dump(json_data, f, indent=2)
    
    print(f"Data exported to {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Report on job execution history")
    
    # Run ID selection
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-r", "--run-id", type=int, help="Specific run ID to report on")
    group.add_argument("-l", "--last", action="store_true", help="Report on the most recent run")
    group.add_argument("-a", "--all", action="store_true", help="Report summary of all runs")
    
    # Filtering and output options
    parser.add_argument("-p", "--pattern", type=str, help="Regex pattern to filter jobs")
    parser.add_argument("-j", "--json", type=str, help="Export report to JSON file (outputs JSON to standard output if no filename is supplied)", nargs='?', const='')
    parser.add_argument("-app", "--application", type=str, help="Application name to filter by (required when using -r/--run-id)")
    
    args = parser.parse_args()
    
    # If no args are provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
        
    # Make application name mandatory when specifying a run-id
    if args.run_id is not None and args.application is None:
        print("Error: --application is required when using --run-id")
        parser.print_help()
        sys.exit(1)
    
    try:
        # Determine which run_id to report on
        if args.all:
            # Get all runs summary
            run_stats = get_all_runs(args.application)
            
            # Check if JSON output is requested
            if args.json is not None:
                # Create JSON data for all runs
                json_data = {"runs": []}
                
                for stat in run_stats:
                    run_id = stat[0]
                    start_time = stat[1]
                    end_time = stat[2]
                    success_count = stat[3]
                    failed_count = stat[4]
                    timeout_count = stat[5]
                    total_jobs = stat[6]
                    application_name = stat[7] if len(stat) > 7 else "unknown"
                    
                    json_data["runs"].append({
                        "run_id": run_id,
                        "application_name": application_name,
                        "start_time": convert_to_eastern(start_time),
                        "end_time": convert_to_eastern(end_time),
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "timeout_count": timeout_count,
                        "total_jobs": total_jobs,
                        "status": "SUCCESS" if failed_count == 0 and timeout_count == 0 else "FAILED"
                    })
                
                if args.json.strip():  # If filename is provided
                    with open(args.json, 'w') as f:
                        json.dump(json_data, f, indent=2)
                    print(f"Data exported to {args.json}")
                else:
                    # Output JSON to standard output
                    print(json.dumps(json_data, indent=2))
            else:
                print_all_runs(run_stats)
            return
            
        if args.last:
            run_id = get_max_run_id(args.application)
            # When using --last with --application, get the last run for that specific application
        elif args.run_id is not None:
            run_id = args.run_id
            # Application is already required and checked above
        else:
            run_id = get_max_run_id()
        
        if run_id == 0:
            print("No runs found in the database.")
            sys.exit(0)
            
        # Get data for the specified run_id with optional pattern filtering and app filtering
        run_data = get_run_data(run_id, args.pattern, args.application)
        
        if not run_data:
            app_msg = f" for application '{args.application}'" if args.application else ""
            print(f"No data found for run_id {run_id}{app_msg}")
            sys.exit(0)
            
        # Export to JSON if requested
        if args.json is not None:
            if args.json.strip():  # If filename is provided and not empty
                export_json(run_data, run_id, args.json)
            else:
                # Output JSON to standard output if no filename is supplied
                application_name = run_data[0][4] if run_data else "unknown"
                json_data = {
                    "run_id": run_id,
                    "application_name": application_name,
                    "jobs": []
                }
                
                for job in run_data:
                    json_data["jobs"].append({
                        "id": job[0],
                        "description": job[1],
                        "command": job[2],
                        "status": job[3],
                        "application_name": job[4],
                        "timestamp": convert_to_eastern(job[5])
                    })
                
                print(json.dumps(json_data, indent=2))
        else:
            # Print the results to the console
            print_run_details(run_data, run_id)
            
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Value error: {e}")
        print("This may be caused by non-integer run_id values in the database.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()