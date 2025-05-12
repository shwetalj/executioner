import sqlite3
import json
from db.sqlite_backend import db_connection
from jobs.db_utils import handle_db_errors

class JobHistoryManager:
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
            cursor.execute("SELECT MAX(CAST(run_id AS INTEGER)) FROM job_history")
            last_run_id = cursor.fetchone()[0]
            return (last_run_id + 1) if last_run_id is not None else 1

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

    def update_job_status(self, job_id, status):
        job = self.jobs[job_id]
        self.job_status_batch.append((
            self.run_id,
            job_id,
            job.get("description", ""),
            job["command"],
            status,
            self.application_name
        ))

    @handle_db_errors(lambda self: self.logger)
    def commit_job_statuses(self):
        if not self.job_status_batch:
            return
        with db_connection(self.logger) as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO job_history
                (run_id, id, description, command, status, application_name)
                VALUES (?, ?, ?, ?, ?, ?)
            """, self.job_status_batch)
            conn.commit()
        self.job_status_batch.clear()

    @handle_db_errors(lambda self: self.logger)
    def update_retry_history(self, job_id, retry_history, retry_count, status, reason=None):
        with db_connection(self.logger) as conn:
            retry_history_json = json.dumps(retry_history)
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(job_history)")
            columns = [col[1] for col in cursor.fetchall()]
            columns_to_add = []
            if 'retry_history' not in columns:
                columns_to_add.append(("retry_history", "TEXT"))
            if 'last_exit_code' not in columns:
                columns_to_add.append(("last_exit_code", "INTEGER"))
            if 'retry_count' not in columns:
                columns_to_add.append(("retry_count", "INTEGER", "DEFAULT 0"))
            if 'last_error' not in columns:
                columns_to_add.append(("last_error", "TEXT"))
            if columns_to_add:
                for col_info in columns_to_add:
                    col_name = col_info[0]
                    col_type = col_info[1]
                    col_constraint = col_info[2] if len(col_info) > 2 else ""
                    alter_sql = f"ALTER TABLE job_history ADD COLUMN {col_name} {col_type} {col_constraint}".strip()
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
                try:
                    cursor.execute("ALTER TABLE job_history ADD COLUMN last_exit_code INTEGER")
                    conn.commit()
                    self.logger.info("Added missing column to job_history: last_exit_code INTEGER")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" not in str(e):
                        self.logger.warning(f"Could not add last_exit_code column: {e}")
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