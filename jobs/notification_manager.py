import smtplib
import ssl
import glob
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from jobs.logging_setup import setup_logging
import os

class NotificationManager:
    def __init__(self, email_address, email_on_success, email_on_failure, smtp_server, smtp_port, smtp_user, smtp_password, application_name, logger=None):
        self.email_address = email_address
        self.email_on_success = email_on_success
        self.email_on_failure = email_on_failure
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.application_name = application_name
        self.logger = logger or setup_logging(application_name, "main")

    def send_notification(self, success, run_id, summary, subject_extra=None, attachments=None):
        # Debug: log the type and value of email_address
        #SSJ self.logger.info(f"Type of email_address: {type(self.email_address)}; Value: {self.email_address}")
        # Normalize email_address to a list of recipients
        if isinstance(self.email_address, str):
            recipients = [addr.strip() for addr in self.email_address.split(",") if addr.strip()]
        elif isinstance(self.email_address, list):
            recipients = [str(addr).strip() for addr in self.email_address if str(addr).strip()]
        else:
            recipients = []
        if not recipients or not any('@' in addr for addr in recipients):
            print(f"DEBUG: email_address type: {type(self.email_address)}, value: {self.email_address}")
            print(f"DEBUG: recipients: {recipients}")
            self.logger.warning(f"Email notifications enabled but email_address is invalid: '{self.email_address}'.")
            return
        if (success and not self.email_on_success) or (not success and not self.email_on_failure):
            return
        subject_status = "SUCCESS" if success else "FAILURE"
        subject = f"[{self.application_name}] Run #{run_id} {subject_status}"
        if subject_extra:
            subject += f" - {subject_extra}"
        message = MIMEMultipart()
        message["From"] = self.smtp_user or (recipients[0] if recipients else "")
        message["To"] = ", ".join(recipients)
        message["Subject"] = subject
        message.attach(MIMEText(summary, "plain"))
        # Attach files if provided
        if attachments:
            for file_path in attachments:
                try:
                    with open(file_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={os.path.basename(file_path)}",
                    )
                    message.attach(part)
                except Exception as e:
                    self.logger.error(f"Failed to attach file {file_path}: {e}")
        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                #server.starttls(context=context)
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(message["From"], recipients, message.as_string())
            self.logger.info(f"Notification email sent to {recipients} for run {run_id}.")
        except Exception as e:
            self.logger.error(f"Failed to send notification email: {e}")

    def generate_execution_summary(self, success, run_id, start_time, end_time, completed_jobs, failed_jobs, skip_jobs, 
                                  jobs_config, dependency_manager, job_log_paths, failed_job_reasons):
        """Generate a comprehensive execution summary for notifications."""
        # Calculate skipped jobs due to dependencies
        skipped_due_to_deps = []
        for job_id in jobs_config:
            if job_id not in completed_jobs and job_id not in failed_jobs and job_id not in skip_jobs:
                unmet = [dep for dep in dependency_manager.get_job_dependencies(job_id) 
                        if dep not in completed_jobs and dep not in skip_jobs]
                failed_unmet = [dep for dep in unmet if dep in failed_jobs]
                skipped_due_to_deps.append((job_id, unmet, failed_unmet))
        
        # Basic summary information
        status = "SUCCESS" if success else "FAILED"
        duration = end_time - start_time if end_time and start_time else None
        duration_str = str(duration).split('.')[0] if duration else "N/A"
        
        summary = (
            f"Application: {self.application_name}\n"
            f"Run ID: {run_id}\n"
            f"Status: {status}\n"
            f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S') if start_time else 'N/A'}\n"
            f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S') if end_time else 'N/A'}\n"
            f"Duration: {duration_str}\n"
            f"Jobs Completed: {len(completed_jobs)}\n"
            f"Jobs Failed: {len(failed_jobs)}\n"
            f"Jobs Skipped: {len(skip_jobs) + len(skipped_due_to_deps)}\n"
        )
        
        # Add failed jobs details - handle both dict and list formats
        if isinstance(jobs_config, dict):
            # jobs_config is a dict like {job_id: job_config}
            failed_job_order = [job_id for job_id in failed_jobs if job_id in jobs_config]
        else:
            # jobs_config is a list like [{"id": job_id, ...}, ...]
            failed_job_order = [j["id"] for j in jobs_config if j["id"] in failed_jobs]
            
        if failed_job_order:
            summary += "\nFailed Jobs:\n"
            for job_id in failed_job_order:
                job_log_path = job_log_paths.get(job_id, None)
                if isinstance(jobs_config, dict):
                    desc = jobs_config[job_id].get('description', '')
                else:
                    desc = next((j.get('description', '') for j in jobs_config if j.get('id') == job_id), '')
                reason = failed_job_reasons.get(job_id, '')
                summary += f"  - {job_id}: {desc}\n      Reason: {reason}"
                if job_log_path:
                    summary += f"\n      Log: {job_log_path}"
                summary += "\n"
        
        # Add skipped jobs details
        if skipped_due_to_deps:
            summary += "\nSkipped Jobs (unmet dependencies):\n"
            for job_id, unmet, failed_unmet in skipped_due_to_deps:
                if isinstance(jobs_config, dict):
                    desc = jobs_config.get(job_id, {}).get('description', '')
                else:
                    desc = next((j.get('description', '') for j in jobs_config if j.get('id') == job_id), '')
                if failed_unmet:
                    summary += f"  - {job_id}: {desc}\n      Skipped (failed dependencies: {', '.join(failed_unmet)}; other unmet: {', '.join([d for d in unmet if d not in failed_unmet])})\n"
                else:
                    summary += f"  - {job_id}: {desc}\n      Skipped (unmet dependencies: {', '.join(unmet)})\n"
        
        return summary

    def collect_log_attachments(self, run_id):
        """Collect all log files for a specific run."""
        from config.loader import Config
        
        # Collect all job log files for this run
        log_pattern = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.job-*.run-{run_id}.log")
        attachments = glob.glob(log_pattern)
        
        # Add main application-level run log
        main_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.run-{run_id}.log")
        if not os.path.exists(main_log_path):
            # Fallback to run-None.log if run_id log does not exist
            main_log_path = os.path.join(Config.LOG_DIR, f"executioner.{self.application_name}.run-None.log")
        if os.path.exists(main_log_path):
            attachments.append(main_log_path)
            
        return attachments
