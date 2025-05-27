import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from jobs.logger_factory import setup_logging
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
                server.starttls(context=context)
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(message["From"], recipients, message.as_string())
            self.logger.info(f"Notification email sent to {recipients} for run {run_id}.")
        except Exception as e:
            self.logger.error(f"Failed to send notification email: {e}") 
