import io
from unittest.mock import MagicMock, patch

from PIL import Image

from events.storage import S3ImageStorageClient


S3_CONFIG = {
    'endpoint_url': 'https://s3.example.com',
    'region_name': 'us-west-1',
    'aws_access_key_id': 'test-key',
    'aws_secret_access_key': 'test-secret',
}


def _jpeg_bytes():
    img = Image.new('RGB', (10, 10), color=(1, 2, 3))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _make_client():
    with patch('events.storage.boto3'):
        return S3ImageStorageClient(S3_CONFIG)


def _parsed_message(bucket='bucket-1', key='users/camera-1/img.jpg',
                     public_camera_id='camera-1'):
    message = MagicMock()
    parsed = MagicMock()
    parsed.bucket = bucket
    parsed.key = key
    parsed.public_camera_id = public_camera_id
    parsed.original_message.return_value = message
    return parsed


# --- __init__ ---

def test_constructor_creates_s3_resource_with_config_credentials():
    with patch('events.storage.boto3') as mock_boto3:
        S3ImageStorageClient(S3_CONFIG)
    mock_boto3.resource.assert_called_once_with(
        's3',
        endpoint_url='https://s3.example.com',
        region_name='us-west-1',
        aws_access_key_id='test-key',
        aws_secret_access_key='test-secret',
    )


def test_constructor_defaults_num_workers_to_ten():
    client = _make_client()
    assert client.num_workers == 10


def test_constructor_accepts_custom_num_workers():
    with patch('events.storage.boto3'):
        client = S3ImageStorageClient(S3_CONFIG, num_workers=3)
    assert client.num_workers == 3


# --- _fetch_image ---

def test_fetch_image_returns_camera_id_and_image_on_success():
    client = _make_client()
    parsed = _parsed_message(public_camera_id='camera-42')
    client.s3_resource.Object.return_value.get.return_value = {
        'Body': io.BytesIO(_jpeg_bytes())
    }

    result = client._fetch_image(parsed)

    camera_id, image = result
    assert camera_id == 'camera-42'
    assert isinstance(image, Image.Image)


def test_fetch_image_requests_correct_bucket_and_key():
    client = _make_client()
    parsed = _parsed_message(bucket='my-bucket', key='users/cam/img.jpg')
    client.s3_resource.Object.return_value.get.return_value = {
        'Body': io.BytesIO(_jpeg_bytes())
    }

    client._fetch_image(parsed)

    client.s3_resource.Object.assert_called_once_with(
        bucket_name='my-bucket', key='users/cam/img.jpg')


def test_fetch_image_does_not_delete_the_message_on_success():
    """Downloading the bytes is not "done with the event".

    This client used to delete on a successful download, which meant a failure
    anywhere later -- rule evaluation, notification writes -- dropped the event
    permanently. Deletion is now the caller's job, after the work commits.
    """
    client = _make_client()
    parsed = _parsed_message()
    client.s3_resource.Object.return_value.get.return_value = {
        'Body': io.BytesIO(_jpeg_bytes())
    }

    client._fetch_image(parsed)

    parsed.original_message.return_value.delete.assert_not_called()


def test_fetch_image_returns_none_when_get_raises():
    client = _make_client()
    parsed = _parsed_message()
    client.s3_resource.Object.return_value.get.side_effect = Exception('boom')

    result = client._fetch_image(parsed)

    assert result is None


def test_fetch_image_does_not_delete_message_when_get_fails():
    client = _make_client()
    parsed = _parsed_message()
    client.s3_resource.Object.return_value.get.side_effect = Exception('boom')

    client._fetch_image(parsed)

    parsed.original_message.return_value.delete.assert_not_called()


def test_fetch_image_returns_none_when_image_bytes_are_corrupt():
    client = _make_client()
    parsed = _parsed_message()
    client.s3_resource.Object.return_value.get.return_value = {
        'Body': io.BytesIO(b'not an image')
    }

    result = client._fetch_image(parsed)

    assert result is None


# --- download_images ---

def test_download_images_groups_by_camera_id():
    client = _make_client()
    messages = [
        _parsed_message(key='users/camera-1/a.jpg', public_camera_id='camera-1'),
        _parsed_message(key='users/camera-1/b.jpg', public_camera_id='camera-1'),
        _parsed_message(key='users/camera-2/c.jpg', public_camera_id='camera-2'),
    ]
    client.s3_resource.Object.return_value.get.side_effect = (
        lambda: {'Body': io.BytesIO(_jpeg_bytes())})

    result = client.download_images(messages)

    assert len(result['camera-1']) == 2
    assert len(result['camera-2']) == 1


def test_download_images_skips_failed_downloads():
    client = _make_client()
    good = _parsed_message(key='users/camera-1/a.jpg', public_camera_id='camera-1')
    bad = _parsed_message(key='users/camera-1/b.jpg', public_camera_id='camera-1')

    def get_side_effect(bucket_name, key):
        obj = MagicMock()
        if key == bad.key:
            obj.get.side_effect = Exception('boom')
        else:
            obj.get.return_value = {'Body': io.BytesIO(_jpeg_bytes())}
        return obj

    client.s3_resource.Object.side_effect = get_side_effect

    result = client.download_images([good, bad])

    assert len(result['camera-1']) == 1


def test_download_images_returns_empty_dict_for_no_messages():
    client = _make_client()
    result = client.download_images([])
    assert dict(result) == {}
