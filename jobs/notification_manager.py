import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import logging
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
        self.logger = logger or logging.getLogger("notification_manager")

    def send_notification(self, success, run_id, summary, subject_extra=None, attachments=None):
        if not self.email_address or '@' not in self.email_address:
            self.logger.warning(f"Email notifications enabled but email_address is invalid: '{self.email_address}'.")
            return
        if (success and not self.email_on_success) or (not success and not self.email_on_failure):
            return
        subject_status = "SUCCESS" if success else "FAILURE"
        subject = f"[{self.application_name}] Run #{run_id} {subject_status}"
        if subject_extra:
            subject += f" - {subject_extra}"
        message = MIMEMultipart()
        message["From"] = self.smtp_user or self.email_address
        message["To"] = self.email_address
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
                server.sendmail(message["From"], self.email_address, message.as_string())
            self.logger.info(f"Notification email sent to {self.email_address} for run {run_id}.")
        except Exception as e:
            self.logger.error(f"Failed to send notification email: {e}") 