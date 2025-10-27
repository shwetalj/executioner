import sqlite3
import logging
import sys
import os
import json
from contextlib import contextmanager
from config.loader import Config
from jobs.logging_setup import setup_logging

def get_logger(application_name="executioner", run_id=None):
    return setup_logging(application_name, run_id or "main")

@contextmanager
def db_connection(logger):
    """Context manager for database connections to ensure proper cleanup."""
    conn = None
    try:
        conn = sqlite3.connect(str(Config.DB_FILE))
        # Set a default busy timeout to prevent immediate errors when database is locked
        conn.execute("PRAGMA busy_timeout = 3000")  # 3 seconds
        yield conn
    except sqlite3.Error as e:
        # Rollback any pending transaction before re-raising
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back transaction due to database error")
            except sqlite3.Error:
                pass  # Connection might be broken
        logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        # Handle non-SQLite exceptions
        if conn is not None:
            try:
                conn.rollback()
                logger.debug("Rolled back transaction due to error")
            except sqlite3.Error:
                pass  # Connection might be broken
        logger.error(f"Unexpected error: {e}")
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")

def init_db(verbose=False, logger=None):
    """Initialize the SQLite database with enhanced schema versioning and migration support."""
    import hashlib  # Import for creating migration hashes
    db_dir = os.path.dirname(os.path.abspath(Config.DB_FILE))
    os.makedirs(db_dir, exist_ok=True)
    log_level = logging.INFO if verbose else logging.DEBUG
    logger = logger or get_logger()
    logger.log(log_level, f"Initializing database at {Config.DB_FILE}")
    db_exists = os.path.exists(Config.DB_FILE)
    if db_exists:
        try:
            with db_connection(logger) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
                if cursor.fetchone():
                    cursor.execute("SELECT MAX(version) FROM schema_version")
                    version = cursor.fetchone()[0]
                    if version is not None:
                        logger.log(log_level, f"Database already initialized (schema version {version})")
                        return
        except sqlite3.Error:
            pass
    try:
        with db_connection(logger) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA busy_timeout = 5000")
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("BEGIN IMMEDIATE TRANSACTION")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS db_init_lock (
                    id INTEGER PRIMARY KEY,
                    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    locked_by TEXT,
                    process_id INTEGER
                )
            """)
            cursor.execute("""
                INSERT OR REPLACE INTO db_init_lock (id, locked_by, process_id)
                VALUES (1, ?, ?)
            """, ("executioner-init", os.getpid()))
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    migration_hash TEXT,
                    script_name TEXT,
                    rollback_info TEXT
                )
            """)
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            current_version = row[0] if row[0] is not None else 0
            migrations = [
                (1, "Initial schema", [
                    """
                    CREATE TABLE IF NOT EXISTS job_history (
                        run_id INTEGER,
                        id TEXT,
                        description TEXT,
                        command TEXT,
                        status TEXT,
                        application_name TEXT,
                        last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (run_id, id)
                    )
                    """,
                    "CREATE INDEX IF NOT EXISTS idx_job_history_run_id ON job_history (run_id)",
                    "CREATE INDEX IF NOT EXISTS idx_job_history_status ON job_history (status)"
                ], None, """
                DROP TABLE IF EXISTS job_history;
                """),
                (2, "Add retry tracking", [
                    "ALTER TABLE job_history ADD COLUMN retry_count INTEGER DEFAULT 0",
                    "ALTER TABLE job_history ADD COLUMN last_error TEXT",
                    "ALTER TABLE job_history ADD COLUMN retry_history TEXT"
                ], None, """
                -- SQLite doesn't support DROP COLUMN, but here's the rollback info
                -- CREATE TABLE backup AS SELECT run_id, id, description, command, status, application_name, last_run FROM job_history;
                -- DROP TABLE job_history;
                -- CREATE TABLE job_history AS SELECT * FROM backup;
                -- DROP TABLE backup;
                """),
                (3, "Add execution metrics", [
                    "ALTER TABLE job_history ADD COLUMN duration_seconds REAL",
                    "ALTER TABLE job_history ADD COLUMN memory_usage_mb REAL",
                    "ALTER TABLE job_history ADD COLUMN cpu_usage_percent REAL"
                ], None, """
                -- SQLite doesn't support DROP COLUMN, but here's the rollback info
                -- CREATE TABLE backup AS SELECT run_id, id, description, command, status, application_name, last_run, retry_count, last_error FROM job_history;
                -- DROP TABLE job_history;
                -- CREATE TABLE job_history AS SELECT * FROM backup;
                -- DROP TABLE backup;
                """),
                (4, "Add migration history tracking", [
                    """
                    CREATE TABLE IF NOT EXISTS migration_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        version_from INTEGER,
                        version_to INTEGER,
                        migration_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT,
                        error_message TEXT
                    )
                    """
                ], None, "DROP TABLE IF EXISTS migration_history;"),
                (5, "Add run summary table", [
                    """
                    CREATE TABLE IF NOT EXISTS run_summary (
                        run_id INTEGER PRIMARY KEY,
                        application_name TEXT NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        status TEXT,
                        total_jobs INTEGER DEFAULT 0,
                        completed_jobs INTEGER DEFAULT 0,
                        failed_jobs INTEGER DEFAULT 0,
                        skipped_jobs INTEGER DEFAULT 0,
                        exit_code INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                    """,
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_app ON run_summary (application_name)",
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_status ON run_summary (status)",
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_start ON run_summary (start_time)"
                ], None, "DROP TABLE IF EXISTS run_summary;"),
                (6, "Add working directory support", [
                    "ALTER TABLE run_summary ADD COLUMN working_dir TEXT"
                ], None, """
                -- SQLite doesn't support DROP COLUMN, but here's the rollback info
                -- CREATE TABLE backup AS SELECT run_id, application_name, start_time, end_time, status, total_jobs, completed_jobs, failed_jobs, skipped_jobs, exit_code, created_at FROM run_summary;
                -- DROP TABLE run_summary;
                -- CREATE TABLE run_summary AS SELECT * FROM backup;
                -- DROP TABLE backup;
                """),
                (7, "Add attempt tracking with composite key", [
                    """
                    -- Create new table with composite primary key
                    CREATE TABLE IF NOT EXISTS run_summary_new (
                        run_id INTEGER NOT NULL,
                        attempt_id INTEGER NOT NULL DEFAULT 1,
                        application_name TEXT NOT NULL,
                        start_time TIMESTAMP NOT NULL,
                        end_time TIMESTAMP,
                        status TEXT,
                        total_jobs INTEGER DEFAULT 0,
                        completed_jobs INTEGER DEFAULT 0,
                        failed_jobs INTEGER DEFAULT 0,
                        skipped_jobs INTEGER DEFAULT 0,
                        exit_code INTEGER,
                        working_dir TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (run_id, attempt_id)
                    )
                    """,
                    """
                    -- Copy existing data with attempt_id = 1 for all existing runs
                    INSERT INTO run_summary_new (run_id, attempt_id, application_name, start_time, 
                                                end_time, status, total_jobs, completed_jobs, 
                                                failed_jobs, skipped_jobs, exit_code, working_dir, created_at)
                    SELECT run_id, 1, application_name, start_time, end_time, status, 
                           total_jobs, completed_jobs, failed_jobs, skipped_jobs, exit_code, 
                           working_dir, created_at
                    FROM run_summary
                    """,
                    "DROP TABLE IF EXISTS run_summary",
                    "ALTER TABLE run_summary_new RENAME TO run_summary",
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_app ON run_summary (application_name)",
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_status ON run_summary (status)",
                    "CREATE INDEX IF NOT EXISTS idx_run_summary_run ON run_summary (run_id)"
                ], None, """
                -- Rollback: restore original table structure
                -- CREATE TABLE run_summary AS SELECT run_id, application_name, start_time, end_time, status, total_jobs, completed_jobs, failed_jobs, skipped_jobs, exit_code, working_dir, created_at FROM run_summary;
                """),
                (8, "Update job_history for composite key", [
                    """
                    -- Create new job_history table with composite key
                    CREATE TABLE IF NOT EXISTS job_history_new (
                        run_id INTEGER NOT NULL,
                        attempt_id INTEGER NOT NULL DEFAULT 1,
                        id TEXT NOT NULL,
                        description TEXT,
                        command TEXT,
                        status TEXT,
                        application_name TEXT,
                        duration_seconds REAL,
                        memory_usage_mb REAL,
                        cpu_usage_percent REAL,
                        retry_count INTEGER DEFAULT 0,
                        last_error TEXT,
                        retry_history TEXT,
                        last_run TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (run_id, attempt_id, id)
                    )
                    """,
                    """
                    -- Copy existing data with attempt_id = 1
                    INSERT INTO job_history_new (run_id, attempt_id, id, description, command, status, 
                                                application_name, duration_seconds, memory_usage_mb, 
                                                cpu_usage_percent, retry_count, last_error, retry_history, last_run)
                    SELECT run_id, 1, id, description, command, status, application_name, 
                           duration_seconds, memory_usage_mb, cpu_usage_percent, retry_count, 
                           last_error, retry_history, last_run
                    FROM job_history
                    """,
                    "DROP TABLE IF EXISTS job_history",
                    "ALTER TABLE job_history_new RENAME TO job_history",
                    "CREATE INDEX IF NOT EXISTS idx_job_history_run ON job_history (run_id, attempt_id)",
                    "CREATE INDEX IF NOT EXISTS idx_job_history_status ON job_history (status)"
                ], None, """
                -- Rollback: restore original job_history structure
                """)
            ]
            migration_id = None
            if current_version < len(migrations):
                try:
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='migration_history'")
                    if cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO migration_history (version_from, version_to, status) VALUES (?, ?, ?)",
                            (current_version, len(migrations), "IN_PROGRESS")
                        )
                        conn.commit()
                        cursor.execute("SELECT last_insert_rowid()")
                        migration_id = cursor.fetchone()[0]
                except sqlite3.Error as e:
                    logger.warning(f"Warning: Could not record migration start: {e}")
            try:
                for version, description, statements, data_migration, rollback in migrations:
                    if version > current_version:
                        logger.info(f"Applying database migration v{version}: {description}")
                        migration_hash = hashlib.md5(str(statements).encode()).hexdigest()
                        for statement in statements:
                            try:
                                cursor.execute(statement)
                            except sqlite3.OperationalError as e:
                                if "duplicate column name" not in str(e):
                                    if migration_id:
                                        error_msg = f"Migration v{version} failed: {e}"
                                        try:
                                            cursor.execute(
                                                "UPDATE migration_history SET status = ?, error_message = ? WHERE id = ?",
                                                ("FAILED", error_msg, migration_id)
                                            )
                                            conn.commit()
                                        except sqlite3.Error:
                                            pass  # Best effort - already handling the main error
                                    raise
                        if data_migration:
                            data_migration(conn, cursor)
                        cursor.execute(
                            """
                            INSERT INTO schema_version
                            (version, description, migration_hash, script_name, rollback_info)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (version, description, migration_hash, f"migration_v{version}", rollback)
                        )
                        conn.commit()
                if migration_id:
                    cursor.execute(
                        "UPDATE migration_history SET status = ? WHERE id = ?",
                        ("COMPLETED", migration_id)
                    )
                    conn.commit()
            except Exception as e:
                if migration_id:
                    try:
                        cursor.execute(
                            "UPDATE migration_history SET status = ?, error_message = ? WHERE id = ?",
                            ("FAILED", str(e), migration_id)
                        )
                        conn.commit()
                    except sqlite3.Error:
                        pass  # Best effort - already handling the main error
                raise
            conn.commit()
            cursor.execute("SELECT MAX(version) FROM schema_version")
            row = cursor.fetchone()
            final_version = row[0] if row[0] is not None else 0
            if final_version > current_version:
                logger.info(f"Database migrated from version {current_version} to {final_version}")
            else:
                logger.info(f"Database schema is up to date (version {final_version})")
            logger.info(f"Database initialization completed successfully")
    except sqlite3.Error as e:
        # Rollback any pending transaction
        try:
            if 'conn' in locals() and conn:
                conn.rollback()
                logger.debug("Transaction rolled back due to error")
        except sqlite3.Error as rollback_error:
            logger.error(f"Failed to rollback transaction: {rollback_error}")
        logger.error(f"Database initialization error: {e}")
        sys.exit(1)
    except Exception as e:
        # Handle non-database exceptions
        try:
            if 'conn' in locals() and conn:
                conn.rollback()
                logger.debug("Transaction rolled back due to error")
        except sqlite3.Error as rollback_error:
            logger.error(f"Failed to rollback transaction: {rollback_error}")
        logger.error(f"Unexpected error during database initialization: {e}")
        sys.exit(1)


