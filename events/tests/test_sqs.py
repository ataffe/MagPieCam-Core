import json
import pytest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.conf import settings

from events.sqs import ParsedSQSMessage, SQSImageQueueClient


def _queue_not_found_error():
    return ClientError(
        {'Error': {'Code': 'AWS.SimpleQueueService.NonExistentQueue',
                    'Message': 'The specified queue does not exist.'}},
        'GetQueueUrl')


SQS_CONFIG = {
    'endpoint_url': 'https://sqs.example.com',
    'region_name': 'us-west-1',
    'aws_access_key_id': 'test-key',
    'aws_secret_access_key': 'test-secret',
    'aws_cert_file': '/fake/cert.pem',
    'sqs': {
        'queue_name': 'test-queue',
        'max_number_of_messages': 5,
        'wait_time_seconds': 10,
        'max_retry_attempts': 10,
        'retry_mode': 'standard',
    },
}


def _sqs_message(body: dict):
    message = MagicMock()
    message.body = json.dumps(body)
    return message


# --- ParsedSQSMessage ---

def test_valid_s3_event_marks_message_as_valid():
    body = {'Records': [{'s3': {
        'bucket': {'name': 'my-bucket'},
        'object': {'key': 'users/camera-1/img.jpg'},
    }}]}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.is_valid is True
    assert parsed.is_test is False


def test_valid_s3_event_extracts_bucket_key_and_camera_id():
    body = {'Records': [{'s3': {
        'bucket': {'name': 'my-bucket'},
        'object': {'key': 'users/camera-1/img.jpg'},
    }}]}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.bucket == 'my-bucket'
    assert parsed.key == 'users/camera-1/img.jpg'
    assert parsed.public_camera_id == 'camera-1'


def test_key_is_url_decoded():
    body = {'Records': [{'s3': {
        'bucket': {'name': 'my-bucket'},
        'object': {'key': 'users/camera-1/my+image%20file.jpg'},
    }}]}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.key == 'users/camera-1/my+image file.jpg'


def test_s3_test_event_is_marked_as_test():
    body = {'Event': 's3:TestEvent'}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.is_test is True
    assert parsed.is_valid is False


def test_message_with_no_records_or_event_is_neither_valid_nor_test():
    body = {'unrelated': 'data'}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.is_valid is False
    assert parsed.is_test is False


def test_message_with_empty_records_is_neither_valid_nor_test():
    body = {'Records': []}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.is_valid is False
    assert parsed.is_test is False


def test_malformed_record_does_not_raise_and_leaves_message_invalid():
    body = {'Records': [{'s3': {'bucket': {'name': 'my-bucket'}}}]}
    parsed = ParsedSQSMessage(_sqs_message(body))
    assert parsed.is_valid is False


def test_original_message_returns_underlying_message():
    message = _sqs_message({'Records': []})
    parsed = ParsedSQSMessage(message)
    assert parsed.original_message() is message


def test_key_bucket_and_public_camera_id_are_read_only_properties():
    body = {'Records': [{'s3': {
        'bucket': {'name': 'my-bucket'},
        'object': {'key': 'users/camera-1/img.jpg'},
    }}]}
    parsed = ParsedSQSMessage(_sqs_message(body))
    with pytest.raises(AttributeError):
        parsed.key = 'other-key'
    with pytest.raises(AttributeError):
        parsed.bucket = 'other-bucket'
    with pytest.raises(AttributeError):
        parsed.public_camera_id = 'other-camera'


# --- SQSImageQueueClient.__init__ ---

def test_constructor_creates_sqs_resource_with_config_credentials():
    with patch('events.sqs.boto3') as mock_boto3:
        SQSImageQueueClient(SQS_CONFIG)
    mock_boto3.resource.assert_called_once()
    args, kwargs = mock_boto3.resource.call_args
    assert args == ('sqs',)
    assert kwargs['endpoint_url'] == 'https://sqs.example.com'
    assert kwargs['region_name'] == 'us-west-1'
    assert kwargs['aws_access_key_id'] == 'test-key'
    assert kwargs['aws_secret_access_key'] == 'test-secret'
    assert kwargs['verify'] == '/fake/cert.pem'


def test_constructor_looks_up_queue_by_configured_name():
    with patch('events.sqs.boto3') as mock_boto3:
        client = SQSImageQueueClient(SQS_CONFIG)
    mock_boto3.resource.return_value.get_queue_by_name.assert_called_once_with(
        QueueName='test-queue')
    assert client.queue is mock_boto3.resource.return_value.get_queue_by_name.return_value


def test_constructor_sets_max_messages_and_wait_time_from_config():
    with patch('events.sqs.boto3'):
        client = SQSImageQueueClient(SQS_CONFIG)
    assert client.max_messages == 5
    assert client.wait_time_seconds == 10


def test_constructor_retries_queue_lookup_when_queue_does_not_exist_yet():
    # Regression test: boto3's own retry config never covers
    # NonExistentQueue (a well-formed 400, not a transient fault), so without
    # an app-level retry this raised on the very first attempt.
    with patch('events.sqs.boto3') as mock_boto3, \
         patch('time.sleep', return_value=None):
        mock_get_queue = mock_boto3.resource.return_value.get_queue_by_name
        mock_get_queue.side_effect = [
            _queue_not_found_error(), _queue_not_found_error(), 'the-resolved-queue']
        client = SQSImageQueueClient(SQS_CONFIG)
    assert client.queue == 'the-resolved-queue'
    assert mock_get_queue.call_count == 3


def test_constructor_gives_up_after_exhausting_queue_lookup_retries():
    with patch('events.sqs.boto3') as mock_boto3, \
         patch('time.sleep', return_value=None):
        mock_get_queue = mock_boto3.resource.return_value.get_queue_by_name
        mock_get_queue.side_effect = _queue_not_found_error()
        with pytest.raises(ClientError):
            SQSImageQueueClient(SQS_CONFIG)
    assert mock_get_queue.call_count == settings.SQS_QUEUE_LOOKUP_RETRIES


def test_constructor_does_not_retry_on_a_non_client_error():
    # A bug in our own code (e.g. a bad config key) shouldn't be masked by
    # eight retries before surfacing.
    with patch('events.sqs.boto3') as mock_boto3, \
         patch('time.sleep', return_value=None):
        mock_get_queue = mock_boto3.resource.return_value.get_queue_by_name
        mock_get_queue.side_effect = TypeError('boom')
        with pytest.raises(TypeError):
            SQSImageQueueClient(SQS_CONFIG)
    assert mock_get_queue.call_count == 1


# --- get_parsed_messages ---

def _make_client_with_messages(*bodies):
    with patch('events.sqs.boto3') as mock_boto3:
        client = SQSImageQueueClient(SQS_CONFIG)
    messages = [_sqs_message(body) for body in bodies]
    client.queue.receive_messages.return_value = messages
    return client, messages


def test_get_parsed_messages_uses_configured_batch_settings():
    client, _ = _make_client_with_messages()
    client.get_parsed_messages()
    client.queue.receive_messages.assert_called_once_with(
        MaxNumberOfMessages=5, WaitTimeSeconds=10)


def test_get_parsed_messages_returns_only_valid_messages():
    valid_body = {'Records': [{'s3': {
        'bucket': {'name': 'b'}, 'object': {'key': 'users/cam-1/i.jpg'},
    }}]}
    invalid_body = {'unrelated': 'data'}
    client, _ = _make_client_with_messages(valid_body, invalid_body)

    parsed_messages = client.get_parsed_messages()

    assert len(parsed_messages) == 1
    assert parsed_messages[0].public_camera_id == 'cam-1'


def test_get_parsed_messages_deletes_test_events_and_excludes_them():
    test_body = {'Event': 's3:TestEvent'}
    client, messages = _make_client_with_messages(test_body)

    parsed_messages = client.get_parsed_messages()

    assert parsed_messages == []
    messages[0].delete.assert_called_once()


def test_get_parsed_messages_does_not_delete_invalid_non_test_messages():
    invalid_body = {'unrelated': 'data'}
    client, messages = _make_client_with_messages(invalid_body)

    client.get_parsed_messages()

    messages[0].delete.assert_not_called()


# --- receipt_handle / delete_message ---

def test_receipt_handle_exposes_the_underlying_handle():
    """The handle is what makes deferred deletion possible: it is a plain
    string, so it survives being passed through a Celery message."""
    message = _sqs_message({'Records': []})
    message.receipt_handle = 'handle-abc'
    parsed = ParsedSQSMessage(message)
    assert parsed.receipt_handle == 'handle-abc'


def test_delete_message_deletes_by_receipt_handle():
    client, _ = _make_client_with_messages()

    client.delete_message('handle-abc')

    client.queue.delete_messages.assert_called_once_with(
        Entries=[{'Id': '1', 'ReceiptHandle': 'handle-abc'}])
