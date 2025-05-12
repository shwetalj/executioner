import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from config.loader import Config

def setup_logging(application_name, run_id):
    """
    Set up and return a logger for the executioner application.
    Includes file, rotating file, and colorized console handlers.
    """
    logger = logging.getLogger('executioner')
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    log_dir = Config.LOG_DIR
    master_log_path = os.path.join(log_dir, f"executioner.{application_name}.run-{run_id}.log")
    app_log_path = os.path.join(log_dir, f"executioner.{application_name}.log")
    file_handler = logging.FileHandler(master_log_path)
    app_file_handler = RotatingFileHandler(app_log_path, maxBytes=Config.MAX_LOG_SIZE, backupCount=Config.BACKUP_LOG_COUNT)
    console_handler = logging.StreamHandler(sys.stdout)
    detailed_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    summary_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [RUN #%(run_id)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(detailed_formatter)
    app_file_handler.setFormatter(summary_formatter)

    class ColorFormatter(logging.Formatter):
        RED = '\033[31m'
        RESET = '\033[0m'
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
        def format(self, record):
            levelname = record.levelname
            if levelname == 'ERROR':
                record.levelname = f"{self.RED}{levelname}{self.RESET}"
            result = super().format(record)
            record.levelname = levelname  # Restore for other handlers
            return result
    color_formatter = ColorFormatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console_handler.setFormatter(color_formatter)

    old_factory = logging.getLogRecordFactory()
    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.run_id = run_id
        record.application_name = application_name
        return record
    logging.setLogRecordFactory(record_factory)

    logger.addHandler(file_handler)
    logger.addHandler(app_file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger 

def setup_job_logger(application_name, run_id, job_id, job_log_path):
    """
    Set up and return a logger for an individual job.
    """
    job_logger = logging.getLogger(f'job_{job_id}')
    job_logger.propagate = False
    for handler in job_logger.handlers[:]:
        job_logger.removeHandler(handler)
    job_file_handler = logging.FileHandler(job_log_path)
    job_file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    job_logger.addHandler(job_file_handler)
    job_logger.setLevel(logging.DEBUG)
    return job_logger, job_file_handler 