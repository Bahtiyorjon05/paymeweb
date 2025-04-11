from celery import shared_task
from django.core.mail import send_mail
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)  # Retry on failure
def send_email_task(self, subject, message, recipient_list):
    """
    Celery task to send an email asynchronously.
    Retries up to 3 times in case of failure.
    """
    try:
        send_mail(subject, message, 'paymebot7@gmail.com', recipient_list)
        logger.info(f"Email sent successfully to {recipient_list}")
        return f"Email sent to {recipient_list}"
    except Exception as exc:
        logger.error(f"Failed to send email to {recipient_list}: {str(exc)}")
        self.retry(exc=exc)  # Retry the task