import logging
from celery import shared_task


from events.processing import process_camera_image
from events.sqs import SQSImageQueueClient
from events.storage import S3ImageStorageClient
from notifications.apns_client import send_notification
logger = logging.getLogger('Events')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluate_camera_image(self, bucket: str, key: str, public_camera_id: str,
                          receipt_handle: str | None = None):
    """Evaluate one uploaded detection image and record any notifications.running.
    """
    storage = S3ImageStorageClient()
    try:
        image = storage.download_image(bucket, key)
    except Exception as exc:
        logger.exception('Failed to download s3://%s/%s', bucket, key)
        raise self.retry(exc=exc)

    notifications = process_camera_image(public_camera_id, image)
    all_notifications_sent = True
    for notification in notifications:
        sent_notification = send_notification(notification)
        all_notifications_sent = all_notifications_sent and sent_notification

    if receipt_handle:
        SQSImageQueueClient().delete_message(receipt_handle)

    return len(notifications)
