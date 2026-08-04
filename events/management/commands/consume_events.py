"""Long-polls SQS for S3 detection-image events and hands each to Celery.
"""
import logging
import signal

from django.core.management.base import BaseCommand

from events.sqs import SQSImageQueueClient
from events.tasks import evaluate_camera_image

logger = logging.getLogger('Events')


class Command(BaseCommand):
    help = 'Poll SQS for camera image events and dispatch them to Celery.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--once',
            action='store_true',
            help='Process a single batch and exit, instead of polling forever.',
        )

    def stop(self, signum=None, frame=None):
        logger.info('Stopping event consumer')
        self._stop = True

    def handle(self, *args, **options):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        queue_client = SQSImageQueueClient()
        logger.info('Event consumer started')

        while not self._stop:
            self._consume_batch(queue_client)
            if options['once']:
                break

        logger.info('Event consumer stopped')

    @staticmethod
    def _consume_batch(queue_client):
        for message in queue_client.get_parsed_messages():
            evaluate_camera_image.delay(
                message.bucket,
                message.key,
                message.public_camera_id,
                message.receipt_handle,
            )
            logger.debug('Dispatched %s/%s for camera %s',
                         message.bucket, message.key, message.public_camera_id)
