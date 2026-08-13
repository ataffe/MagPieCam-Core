import logging
from celery import shared_task

from django.conf import settings
from camera.media_keys import CLIP_PREFIX, detection_key, parse_media_key
from events.processing import process_camera_image
from events.sqs import SQSImageQueueClient
from events.storage import get_s3_image_storage_client
from notifications.apns_client import send_notification
from notifications.models import Notification
logger = logging.getLogger('Events')


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def evaluate_camera_image(self, bucket: str, key: str, public_camera_id: str,
                          receipt_handle: str | None = None):
    """Evaluate one uploaded detection image and record any notifications.running.
    """
    storage = get_s3_image_storage_client()
    try:
        image = storage.download_image(bucket, key)
    except Exception as exc:
        logger.exception('Failed to download s3://%s/%s', bucket, key)
        raise self.retry(exc=exc)

    notification = process_camera_image(public_camera_id, image, detection_image_key=key)

    if notification is None:
        # Nothing fired, so there is nothing left to do with this image.
        if receipt_handle:
            SQSImageQueueClient().delete_message(receipt_handle)
        return 0

    try:
        detection_preview_url = storage.get_image_download_url(bucket, key)
    except Exception as exc:
        logger.exception('Failed to generate download url for s3://%s/%s', bucket, key)
        raise self.retry(exc=exc)

    if settings.VPN_IP:
        detection_preview_url = detection_preview_url.replace(settings.DEV_IP, settings.VPN_IP)

    if not send_notification(notification, detection_preview_url):
        # Leave the message on the queue so the push is retried from scratch.
        notification.delete()
        return 0

    notification.visible = True
    notification.save(update_fields=['visible'])

    if receipt_handle:
        SQSImageQueueClient().delete_message(receipt_handle)

    return 1


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def attach_video_clip(self, bucket: str, key: str, public_camera_id: str,
                      receipt_handle: str | None = None):
    """
    Record that the clip paired with detection still has landed in S3.
    """
    parsed_key = parse_media_key(key)
    attached = 0

    if parsed_key is None or parsed_key.prefix != CLIP_PREFIX:
        logger.warning('Ignoring malformed clip key s3://%s/%s', bucket, key)
    else:
        # Every rule that fired on the detection still is bundled into one
        # notification, so this matches at most one row.
        attached = Notification.objects.filter(
            camera__public_camera_id=public_camera_id,
            detection_image_key=detection_key(public_camera_id, parsed_key.stem),
        ).update(video_clip_key=key)
        if attached == 0:
            storage = get_s3_image_storage_client()
            storage.delete_object(bucket, key)
            logger.warning(
                'No notifications found for s3://%s/%s; deleting clip', bucket, key
            )
        else:
            logger.info('Attached clip %s to %d notification(s)', key, attached)

    if receipt_handle:
        SQSImageQueueClient().delete_message(receipt_handle)

    return attached
