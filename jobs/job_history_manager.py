import sqlite3
import json
from db.sqlite_backend import db_connection

class JobHistoryManager:
    def __init__(self, jobs, application_name, run_id, logger):
        self.jobs = jobs
        self.application_name = application_name
        self.run_id = run_id
        self.logger = logger
        self.job_status_batch = []

    def get_new_run_id(self):
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(CAST(run_id AS INTEGER)) FROM job_history")
                last_run_id = cursor.fetchone()[0]
                return (last_run_id + 1) if last_run_id is not None else 1
        except (sqlite3.Error, ValueError, TypeError):
            self.logger.warning("Could not determine last run_id from database, starting with run_id=1")
            return 1

    def get_previous_run_status(self, resume_run_id):
        job_statuses = {}
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, status FROM job_history WHERE run_id = ?", (resume_run_id,))
                job_statuses = {row[0]: row[1] for row in cursor.fetchall()}
            current_jobs = set(self.jobs.keys())
            previous_jobs = set(job_statuses.keys())
            if current_jobs != previous_jobs:
                if added_jobs := current_jobs - previous_jobs:
                    self.logger.warning(f"New jobs not in previous run: {', '.join(added_jobs)}")
                if removed_jobs := previous_jobs - current_jobs:
                    self.logger.warning(f"Jobs from previous run not in current config: {', '.join(removed_jobs)}")
            return job_statuses
        except sqlite3.Error as e:
            self.logger.error(f"Database error while getting previous run status: {e}")
            return {}

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

    def commit_job_statuses(self):
        if not self.job_status_batch:
            return
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany("""
                    INSERT OR REPLACE INTO job_history
                    (run_id, id, description, command, status, application_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, self.job_status_batch)
                conn.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Database batch update error: {e}")
        finally:
            self.job_status_batch.clear()

    def update_retry_history(self, job_id, retry_history, retry_count, status, reason=None):
        try:
            with db_connection() as conn:
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
        except sqlite3.Error as e:
            self.logger.warning(f"Failed to update retry history for job {job_id}: {e}")

    def get_last_exit_code(self, job_id):
        try:
            with db_connection() as conn:
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
        except (sqlite3.Error, ValueError) as e:
            self.logger.debug(f"Could not retrieve exit code for job {job_id}: {e}")
            return None 