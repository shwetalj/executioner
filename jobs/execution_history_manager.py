import sqlite3
import json
from db.sqlite_connection import db_connection
from jobs.db_utils import handle_db_errors
from jobs.json_utils import to_json

class ExecutionHistoryManager:
    def __init__(self, jobs, application_name, run_id, logger):
        self.jobs = jobs
        self.application_name = application_name
        self.run_id = run_id
        self.logger = logger
        self.job_status_batch = []

    def set_logger(self, logger):
        self.logger = logger

    @handle_db_errors(lambda self: self.logger)
    def get_new_run_id(self):
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            # Check both job_history and run_summary tables to get the highest run_id
            cursor.execute("""
                SELECT MAX(run_id) FROM (
                    SELECT CAST(run_id AS INTEGER) as run_id FROM job_history
                    UNION ALL
                    SELECT run_id FROM run_summary
                )
            """)
            last_run_id = cursor.fetchone()[0]
            return (last_run_id + 1) if last_run_id is not None else 1
    
    @handle_db_errors(lambda self: self.logger)
    def create_run_summary(self, run_id, application_name, start_time, total_jobs, working_dir=None):
        """Create a new run summary entry"""
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO run_summary (run_id, application_name, start_time, status, total_jobs, working_dir)
                    VALUES (?, ?, ?, 'RUNNING', ?, ?)
                """, (run_id, application_name, start_time.strftime('%Y-%m-%d %H:%M:%S'), total_jobs, working_dir))
                conn.commit()
            except Exception as e:
                # Handle the case where run_summary already exists (e.g., from previous run or race condition)
                if "UNIQUE constraint failed" in str(e):
                    self.logger.debug(f"Run summary already exists for run ID {run_id}, skipping creation")
                    # Check if it's truly a duplicate or if we need to update
                    cursor.execute("SELECT COUNT(*) FROM run_summary WHERE run_id = ?", (run_id,))
                    if cursor.fetchone()[0] > 0:
                        return  # Already exists, that's fine
                raise  # Re-raise if it's a different error
    
    @handle_db_errors(lambda self: self.logger)
    def update_run_summary(self, run_id, end_time, status, completed_jobs, failed_jobs, skipped_jobs, exit_code):
        """Update run summary with final results"""
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE run_summary 
                SET end_time = ?, status = ?, completed_jobs = ?, 
                    failed_jobs = ?, skipped_jobs = ?, exit_code = ?
                WHERE run_id = ?
            """, (end_time.strftime('%Y-%m-%d %H:%M:%S'), status, 
                  completed_jobs, failed_jobs, skipped_jobs, exit_code, run_id))
            conn.commit()

    @handle_db_errors(lambda self: self.logger)
    def get_previous_run_status(self, resume_run_id):
        job_statuses = {}
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, status FROM job_history WHERE run_id = ?", (resume_run_id,))
            job_statuses = {row[0]: row[1] for row in cursor.fetchall()}
        current_jobs = set(self.jobs.keys())
        previous_jobs = set(job_statuses.keys())
        if current_jobs != previous_jobs:
            added_jobs = current_jobs - previous_jobs
            if added_jobs:
                self.logger.warning(f"New jobs not in previous run: {', '.join(added_jobs)}")
            removed_jobs = previous_jobs - current_jobs
            if removed_jobs:
                self.logger.warning(f"Jobs from previous run not in current config: {', '.join(removed_jobs)}")
        return job_statuses
    
    @handle_db_errors(lambda self: self.logger)
    def get_recent_runs(self, limit=20, app_name=None):
        """Get recent runs with summary information"""
        runs = []
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            
            # First check if run_summary table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='run_summary'")
            has_run_summary = cursor.fetchone() is not None
            
            if has_run_summary:
                # Use run_summary table for accurate timing
                if app_name:
                    query = """
                    SELECT 
                        rs.run_id,
                        rs.application_name,
                        rs.start_time,
                        rs.end_time,
                        rs.status,
                        rs.total_jobs,
                        rs.completed_jobs as successful_jobs,
                        rs.failed_jobs,
                        rs.skipped_jobs
                    FROM run_summary rs
                    WHERE rs.application_name = ?
                    ORDER BY rs.run_id DESC
                    LIMIT ?
                    """
                    cursor.execute(query, (app_name, limit))
                else:
                    query = """
                    SELECT 
                        rs.run_id,
                        rs.application_name,
                        rs.start_time,
                        rs.end_time,
                        rs.status,
                        rs.total_jobs,
                        rs.completed_jobs as successful_jobs,
                        rs.failed_jobs,
                        rs.skipped_jobs
                    FROM run_summary rs
                    ORDER BY rs.run_id DESC
                    LIMIT ?
                    """
                    cursor.execute(query, (limit,))
                    
                for row in cursor.fetchall():
                    run_id, app_name, start_time, end_time, status, total_jobs, successful_jobs, failed_jobs, skipped_jobs = row
                    
                    # If this run isn't in run_summary but is in job_history, fall back to old method
                    if not start_time:
                        continue
                        
                    # Calculate duration if both times exist
                    duration = 'N/A'
                    if start_time and end_time:
                        try:
                            from datetime import datetime
                            start_dt = datetime.fromisoformat(start_time.replace(' ', 'T'))
                            end_dt = datetime.fromisoformat(end_time.replace(' ', 'T'))
                            duration_td = end_dt - start_dt
                            # Format duration as HH:MM:SS
                            hours, remainder = divmod(int(duration_td.total_seconds()), 3600)
                            minutes, seconds = divmod(remainder, 60)
                            duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        except:
                            duration = 'N/A'
                    
                    # Format job summary
                    job_summary = f"{successful_jobs}/{total_jobs}"
                    if failed_jobs > 0:
                        job_summary += f" ({failed_jobs} failed)"
                    
                    runs.append({
                        'run_id': run_id,
                        'application_name': app_name or 'Unknown',
                        'status': status,
                        'start_time': start_time or 'N/A',
                        'duration': duration,
                        'job_summary': job_summary,
                        'total_jobs': total_jobs,
                        'successful_jobs': successful_jobs,
                        'failed_jobs': failed_jobs,
                        'skipped_jobs': skipped_jobs
                    })
            
            # Also get runs from job_history that might not be in run_summary yet
            if app_name:
                query = """
                SELECT 
                    jh.run_id,
                    jh.application_name,
                    MIN(jh.last_run) as start_time,
                    MAX(jh.last_run) as end_time,
                    COUNT(DISTINCT jh.id) as total_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status = 'SUCCESS' THEN jh.id END) as successful_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status IN ('FAILED', 'ERROR', 'TIMEOUT') THEN jh.id END) as failed_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status = 'SKIPPED' THEN jh.id END) as skipped_jobs
                FROM job_history jh
                WHERE jh.application_name = ?
                    AND jh.run_id NOT IN (SELECT run_id FROM run_summary)
                GROUP BY jh.run_id, jh.application_name
                ORDER BY jh.run_id DESC
                LIMIT ?
                """
                cursor.execute(query, (app_name, limit))
            else:
                query = """
                SELECT 
                    jh.run_id,
                    jh.application_name,
                    MIN(jh.last_run) as start_time,
                    MAX(jh.last_run) as end_time,
                    COUNT(DISTINCT jh.id) as total_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status = 'SUCCESS' THEN jh.id END) as successful_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status IN ('FAILED', 'ERROR', 'TIMEOUT') THEN jh.id END) as failed_jobs,
                    COUNT(DISTINCT CASE WHEN jh.status = 'SKIPPED' THEN jh.id END) as skipped_jobs
                FROM job_history jh"""
                if has_run_summary:
                    query += " WHERE jh.run_id NOT IN (SELECT run_id FROM run_summary)"
                query += """
                GROUP BY jh.run_id, jh.application_name
                ORDER BY jh.run_id DESC
                LIMIT ?
                """
                cursor.execute(query, (limit,))
            
            for row in cursor.fetchall():
                run_id, app_name, start_time, end_time, total_jobs, successful_jobs, failed_jobs, skipped_jobs = row
                
                # Determine overall status
                if failed_jobs > 0:
                    status = 'FAILED'
                elif successful_jobs == total_jobs:
                    status = 'SUCCESS'
                elif successful_jobs > 0:
                    status = 'PARTIAL'
                else:
                    status = 'PENDING'
                
                # Calculate duration if both times exist
                duration = 'N/A'
                if start_time and end_time:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(start_time.replace(' ', 'T'))
                        end_dt = datetime.fromisoformat(end_time.replace(' ', 'T'))
                        duration_td = end_dt - start_dt
                        # Format duration as HH:MM:SS
                        hours, remainder = divmod(int(duration_td.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    except:
                        duration = 'N/A'
                
                # Format job summary
                job_summary = f"{successful_jobs}/{total_jobs}"
                if failed_jobs > 0:
                    job_summary += f" ({failed_jobs} failed)"
                
                runs.append({
                    'run_id': run_id,
                    'application_name': app_name or 'Unknown',
                    'status': status,
                    'start_time': start_time or 'N/A',
                    'duration': duration,
                    'job_summary': job_summary,
                    'total_jobs': total_jobs,
                    'successful_jobs': successful_jobs,
                    'failed_jobs': failed_jobs,
                    'skipped_jobs': skipped_jobs
                })
        
        # Sort runs by run_id descending and limit to requested amount
        runs.sort(key=lambda x: x['run_id'], reverse=True)
        return runs[:limit]
    
    @handle_db_errors(lambda self: self.logger)
    def get_job_statuses_for_run(self, run_id, job_ids=None):
        """Get job statuses for a specific run"""
        statuses = {}
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            if job_ids:
                placeholders = ','.join(['?' for _ in job_ids])
                query = f"SELECT id, status FROM job_history WHERE run_id = ? AND id IN ({placeholders})"
                cursor.execute(query, [run_id] + job_ids)
            else:
                query = "SELECT id, status FROM job_history WHERE run_id = ?"
                cursor.execute(query, (run_id,))
            
            for row in cursor.fetchall():
                statuses[row[0]] = row[1]
        
        return statuses
    
    @handle_db_errors(lambda self: self.logger)
    def mark_jobs_successful(self, run_id, job_ids):
        """Mark specified jobs as successful"""
        success_count = 0
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            
            for job_id in job_ids:
                try:
                    # Update the job status to SUCCESS
                    cursor.execute("""
                        UPDATE job_history 
                        SET status = 'SUCCESS',
                            last_run = CURRENT_TIMESTAMP
                        WHERE run_id = ? AND id = ? AND status IN ('FAILED', 'ERROR', 'TIMEOUT')
                    """, (run_id, job_id))
                    
                    if cursor.rowcount > 0:
                        success_count += 1
                        self.logger.info(f"Marked job {job_id} as SUCCESS for run {run_id}")
                    
                except sqlite3.Error as e:
                    self.logger.error(f"Failed to mark job {job_id} as successful: {e}")
            
            conn.commit()
        
        return success_count
    
    @handle_db_errors(lambda self: self.logger)
    def get_run_details(self, run_id):
        """Get detailed information about a specific run including all job statuses"""
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            
            # First try to get info from run_summary table
            cursor.execute("""
                SELECT application_name, start_time, end_time, status, 
                       total_jobs, completed_jobs, failed_jobs, skipped_jobs, working_dir
                FROM run_summary
                WHERE run_id = ?
            """, (run_id,))
            
            summary_row = cursor.fetchone()
            
            if summary_row:
                # Use run_summary data
                app_name, start_time, end_time, status, total_jobs, completed_jobs, failed_jobs, skipped_jobs, working_dir = summary_row
                
                # Calculate duration
                duration = 'N/A'
                if start_time and end_time:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(start_time.replace(' ', 'T'))
                        end_dt = datetime.fromisoformat(end_time.replace(' ', 'T'))
                        duration_td = end_dt - start_dt
                        hours, remainder = divmod(int(duration_td.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    except Exception as e:
                        self.logger.debug(f"Error calculating duration from run_summary: {e}")
                        duration = 'N/A'
            else:
                # Fallback to old method for backward compatibility
                query = """
                SELECT 
                    application_name,
                    MIN(last_run) as start_time,
                    MAX(last_run) as end_time,
                    COUNT(DISTINCT id) as total_jobs,
                    COUNT(DISTINCT CASE WHEN status = 'SUCCESS' THEN id END) as successful_jobs,
                    COUNT(DISTINCT CASE WHEN status IN ('FAILED', 'ERROR', 'TIMEOUT') THEN id END) as failed_jobs,
                    COUNT(DISTINCT CASE WHEN status = 'SKIPPED' THEN id END) as skipped_jobs
                FROM job_history
                WHERE run_id = ?
                GROUP BY application_name
                """
                
                cursor.execute(query, (run_id,))
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                app_name, start_time, end_time, total_jobs, successful_jobs, failed_jobs, skipped_jobs = row
                completed_jobs = successful_jobs
                
                # Determine overall status
                if failed_jobs > 0:
                    status = 'FAILED'
                elif successful_jobs == total_jobs:
                    status = 'SUCCESS'
                elif successful_jobs > 0:
                    status = 'PARTIAL'
                else:
                    status = 'PENDING'
                
                # Calculate duration (will likely be N/A for old data)
                duration = 'N/A'
                if start_time and end_time:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(start_time.replace(' ', 'T'))
                        end_dt = datetime.fromisoformat(end_time.replace(' ', 'T'))
                        duration_td = end_dt - start_dt
                        hours, remainder = divmod(int(duration_td.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        duration = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    except Exception as e:
                        self.logger.debug(f"Error calculating duration from job_history: {e}")
                        duration = 'N/A'
                
                # No working_dir available in fallback mode
                working_dir = None
            
            run_info = {
                'run_id': run_id,
                'application_name': app_name,
                'status': status,
                'start_time': start_time or 'N/A',
                'end_time': end_time or 'N/A',
                'duration': duration,
                'total_jobs': total_jobs,
                'successful_jobs': completed_jobs if summary_row else successful_jobs,
                'failed_jobs': failed_jobs,
                'skipped_jobs': skipped_jobs,
                'working_dir': working_dir
            }
            
            # Get individual job details
            cursor.execute("""
                SELECT id, description, command, status, last_run, duration_seconds
                FROM job_history
                WHERE run_id = ?
                ORDER BY last_run
            """, (run_id,))
            
            jobs = []
            for job_row in cursor.fetchall():
                job_id, description, command, job_status, last_run, duration_seconds = job_row
                
                # Calculate end time from start time and duration
                end_time = None
                if last_run and duration_seconds is not None:
                    try:
                        from datetime import datetime, timedelta
                        start_dt = datetime.fromisoformat(last_run.replace(' ', 'T'))
                        end_dt = start_dt + timedelta(seconds=duration_seconds)
                        end_time = end_dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                jobs.append({
                    'id': job_id,
                    'description': description or '',
                    'command': command or '',
                    'status': job_status,
                    'last_run': last_run,
                    'duration_seconds': duration_seconds,
                    'end_time': end_time
                })
            
            return {
                'run_info': run_info,
                'jobs': jobs
            }

    def update_job_status(self, job_id, status, duration=None, start_time=None):
        job = self.jobs[job_id]
        self.job_status_batch.append((
            self.run_id,
            job_id,
            job.get("description", ""),
            job["command"],
            status,
            self.application_name,
            start_time,  # last_run timestamp
            duration     # duration_seconds
        ))

    @handle_db_errors(lambda self: self.logger)
    def commit_job_statuses(self):
        if not self.job_status_batch:
            return
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO job_history
                (run_id, id, description, command, status, application_name, last_run, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, self.job_status_batch)
            conn.commit()
        self.job_status_batch.clear()

    # Define allowed columns to prevent SQL injection
    ALLOWED_COLUMNS = {
        'retry_history': ('TEXT', ''),
        'last_exit_code': ('INTEGER', ''),
        'retry_count': ('INTEGER', 'DEFAULT 0'),
        'last_error': ('TEXT', ''),
        'duration_seconds': ('REAL', ''),
        'memory_usage_mb': ('REAL', ''),
        'cpu_usage_percent': ('REAL', '')
    }

    @handle_db_errors(lambda self: self.logger)
    def update_retry_history(self, job_id, retry_history, retry_count, status, reason=None):
        with db_connection(self.logger) as conn:
            retry_history_json = to_json(retry_history)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(job_history)")
            columns = [col[1] for col in cursor.fetchall()]
            columns_to_add = []
            
            # Check which allowed columns need to be added
            for col_name, (col_type, col_constraint) in self.ALLOWED_COLUMNS.items():
                if col_name in ['retry_history', 'last_exit_code', 'retry_count', 'last_error']:
                    if col_name not in columns:
                        columns_to_add.append((col_name, col_type, col_constraint))
            
            if columns_to_add:
                for col_name, col_type, col_constraint in columns_to_add:
                    # Validate column name and type against whitelist
                    if col_name not in self.ALLOWED_COLUMNS:
                        self.logger.error(f"Attempted to add non-whitelisted column: {col_name}")
                        continue
                    
                    # Build SQL with validated components
                    if col_constraint:
                        alter_sql = f"ALTER TABLE job_history ADD COLUMN {col_name} {col_type} {col_constraint}"
                    else:
                        alter_sql = f"ALTER TABLE job_history ADD COLUMN {col_name} {col_type}"
                    
                    try:
                        cursor.execute(alter_sql)
                        self.logger.info(f"Added missing column to job_history: {col_name} {col_type}")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e):
                            raise
                conn.commit()
            cursor.execute(
                "SELECT 1 FROM job_history WHERE run_id = ? AND id = ?",
                (self.run_id, job_id)
            )
            if not cursor.fetchone():
                job = self.jobs[job_id]
                cursor.execute(
                    """
                    INSERT INTO job_history
                    (run_id, id, description, command, status, application_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.run_id,
                        job_id,
                        job.get("description", ""),
                        job["command"],
                        status,
                        self.application_name
                    )
                )
                conn.commit()
            try:
                if reason:
                    cursor.execute(
                        """
                        UPDATE job_history 
                        SET retry_count = ?, retry_history = ?, last_error = ?
                        WHERE run_id = ? AND id = ?
                        """,
                        (retry_count, retry_history_json, reason, self.run_id, job_id)
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE job_history 
                        SET retry_count = ?, retry_history = ?
                        WHERE run_id = ? AND id = ?
                        """,
                        (retry_count, retry_history_json, self.run_id, job_id)
                    )
                conn.commit()
            except sqlite3.OperationalError as e:
                self.logger.warning(f"Could not update retry history, possible schema issue: {e}")
            self.logger.debug(f"Updated retry history for job {job_id}: status={status}, retry_count={retry_count}")

    @handle_db_errors(lambda self: self.logger)
    def get_last_exit_code(self, job_id):
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(job_history)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'last_exit_code' not in columns:
                # Validate column name against whitelist
                if 'last_exit_code' in self.ALLOWED_COLUMNS:
                    col_type, col_constraint = self.ALLOWED_COLUMNS['last_exit_code']
                    try:
                        cursor.execute("ALTER TABLE job_history ADD COLUMN last_exit_code INTEGER")
                        conn.commit()
                        self.logger.info("Added missing column to job_history: last_exit_code INTEGER")
                    except sqlite3.OperationalError as e:
                        if "duplicate column name" not in str(e):
                            self.logger.warning(f"Could not add last_exit_code column: {e}")
                else:
                    self.logger.error("Attempted to add non-whitelisted column: last_exit_code")
                return None
            try:
                cursor.execute(
                    "SELECT last_exit_code FROM job_history WHERE run_id = ? AND id = ?",
                    (self.run_id, job_id)
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
            except sqlite3.OperationalError as e:
                self.logger.debug(f"Error selecting last_exit_code: {e}")
            return None 

