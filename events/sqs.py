from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from urllib.parse import unquote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from django.conf import settings
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from events.interfaces import ImageQueueClient, ParsedMessage

if TYPE_CHECKING:
    # Type stubs only; keeps boto3-stubs out of the runtime image.
    from mypy_boto3_sqs.service_resource import Message

logger = logging.getLogger("SQS Client")


def sqs_config_from_settings() -> dict:
    """
    Kept separate from the client so tests can pass a config straight in.
    """
    return {
        'endpoint_url': settings.AWS_ENDPOINT_URL,
        'region_name': settings.AWS_REGION,
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
        'aws_cert_file': settings.AWS_CERT_FILE_PATH,
        'sqs': {
            'queue_name': settings.SQS_QUEUE_NAME,
            'max_number_of_messages': settings.SQS_MAX_NUMBER_OF_MESSAGES,
            'wait_time_seconds': settings.SQS_WAIT_TIME_SECONDS,
            'max_retry_attempts': settings.SQS_MAX_RETRY_ATTEMPTS,
            'retry_mode': settings.SQS_RETRY_MODE,
        },
    }


class ParsedSQSMessage(ParsedMessage):
    def __init__(self, message: Message):
        self.message = message
        self.is_test = False
        self.is_valid = False
        self._key = None
        self._public_camera_id = None
        self._bucket = None
        msg_body = json.loads(self.message.body)
        try:
            if 'Event' in msg_body and msg_body['Event'] == 's3:TestEvent':
                self.is_test = True
            elif 'Records' in msg_body and len(msg_body['Records']) > 0:
                s3_object_info = msg_body['Records'][0]['s3']
                self._bucket = s3_object_info['bucket']['name']
                self._key = unquote(s3_object_info['object']['key'])
                self._public_camera_id = self._key.split('/')[1]
                self.is_valid = True
        except Exception as e:
            logger.error(f'Error while parsing message: {e} | Message: {json.dumps(msg_body, indent=4)}')

    @property
    def key(self) -> str:
        return self._key

    @property
    def public_camera_id(self) -> str:
        return self._public_camera_id

    @property
    def bucket(self) -> str:
        return self._bucket

    @property
    def receipt_handle(self) -> str:
        return self.message.receipt_handle

    def original_message(self) -> Message:
        return self.message


@retry(
    stop=stop_after_attempt(settings.SQS_QUEUE_LOOKUP_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=retry_if_exception_type(ClientError),
    reraise=True)
def _get_queue_by_name(sqs_resource, queue_name: str):
    """Resolve the queue URL, retrying while it doesn't exist yet.
    """
    return sqs_resource.get_queue_by_name(QueueName=queue_name)


class SQSImageQueueClient(ImageQueueClient):
    def __init__(self, config_dict=None):
        config_dict = config_dict or sqs_config_from_settings()
        self.sqs_resource = boto3.resource(
            'sqs',
            endpoint_url=config_dict['endpoint_url'],
            region_name=config_dict['region_name'],
            aws_access_key_id=config_dict['aws_access_key_id'],
            aws_secret_access_key=config_dict['aws_secret_access_key'],
            verify=config_dict['aws_cert_file'],
            config=Config(
                retries={
                'max_attempts': config_dict['sqs']['max_retry_attempts'],
                'mode': config_dict['sqs']['retry_mode']
            })
        )
        self.queue = _get_queue_by_name(self.sqs_resource, config_dict['sqs']['queue_name'])
        self.max_messages = config_dict['sqs']['max_number_of_messages']
        self.wait_time_seconds = config_dict['sqs']['wait_time_seconds']

    def get_parsed_messages(self) -> list:
        messages = self.queue.receive_messages(
            MaxNumberOfMessages=self.max_messages,
            WaitTimeSeconds=self.wait_time_seconds
        )
        logger.debug(f"Received {len(messages)} messages")
        parsed_messages = []
        for message in messages:
            parsed_message = ParsedSQSMessage(message)
            if parsed_message.is_test:
                message.delete()  # Ignore AWS S3:TestMessage
            elif parsed_message.is_valid:
                parsed_messages.append(parsed_message)
        return parsed_messages

    def delete_message(self, receipt_handle: str):
        """Drop a message once its work is done.
        """
        self.queue.delete_messages(Entries=[{
            'Id': '1',
            'ReceiptHandle': receipt_handle,
        }])
