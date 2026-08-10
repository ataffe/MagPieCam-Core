import os
import pytest
from pathlib import Path
from unittest.mock import patch

from events.ml.weights import (
    download_weights_backblaze,
    weights_ready,
    _WEIGHTS_READY_MARKER,
)


S3_ENV = {
    'OBJ_STORE_ML_BUCKET': 'test-bucket',
    'OBJ_STORE_ENDPOINT_URL': 'https://s3.example.com',
    'OBJ_STORE_ACCESS_KEY_ID': 'test-key',
    'OBJ_STORE_SECRET_ACCESS_KEY': 'test-secret',
}

ONE_FILE_PAGE = [
    {'Contents': [{'Key': 'gemma4/test-variant/model.safetensors'}]}
]


def _make_file_on_download(bucket, key, dest):
    Path(dest).touch()


# --- S3 client setup ---

def test_creates_s3_client_with_credentials_from_env(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        paginator = mock_s3.get_paginator.return_value
        paginator.paginate.return_value = ONE_FILE_PAGE
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    mock_boto3.assert_called_once_with(
        service_name='s3',
        endpoint_url='https://s3.example.com',
        aws_access_key_id='test-key',
        aws_secret_access_key='test-secret',
    )


def test_paginates_with_correct_bucket_and_prefix(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        mock_paginator = mock_s3.get_paginator.return_value
        mock_paginator.paginate.return_value = ONE_FILE_PAGE
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    mock_paginator.paginate.assert_called_once_with(
        Bucket='test-bucket',
        Prefix='gemma4/test-variant/',
    )


# --- File downloading ---

def test_downloads_each_file_in_pages(tmp_path):
    pages = [{'Contents': [
        {'Key': 'gemma4/test-variant/model.safetensors'},
        {'Key': 'gemma4/test-variant/tokenizer.json'},
    ]}]
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        mock_s3.get_paginator.return_value.paginate.return_value = pages
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    assert mock_s3.download_file.call_count == 2


def test_downloads_file_to_correct_destination(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        paginator = mock_s3.get_paginator.return_value
        paginator.paginate.return_value = ONE_FILE_PAGE
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    mock_s3.download_file.assert_called_once_with(
        'test-bucket',
        'gemma4/test-variant/model.safetensors',
        f'{tmp_path}/model.safetensors',
    )


def test_creates_download_directory_if_it_does_not_exist(tmp_path):
    weights_dir = tmp_path / 'new_weights_dir'
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        paginator = mock_s3.get_paginator.return_value
        paginator.paginate.return_value = ONE_FILE_PAGE
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(weights_dir))
    assert weights_dir.exists()


# --- Error handling ---

def test_raises_file_not_found_when_page_has_no_contents(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_boto3.return_value.get_paginator.return_value \
            .paginate.return_value = [{'Contents': []}]
        with pytest.raises(FileNotFoundError):
            download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))


def test_raises_file_not_found_when_no_pages_returned(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_boto3.return_value.get_paginator.return_value \
            .paginate.return_value = []
        with pytest.raises(FileNotFoundError):
            download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))


# --- Completion marker / partial-download recovery ---

def _run_download(tmp_path, pages):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        mock_s3.get_paginator.return_value.paginate.return_value = pages
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))


def test_weights_ready_is_false_without_marker(tmp_path):
    (tmp_path / 'model.safetensors').touch()
    assert weights_ready(str(tmp_path)) is False


def test_writes_ready_marker_after_successful_download(tmp_path):
    _run_download(tmp_path, ONE_FILE_PAGE)
    assert (tmp_path / _WEIGHTS_READY_MARKER).exists()
    assert weights_ready(str(tmp_path)) is True


def test_no_marker_written_when_download_fails(tmp_path):
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_boto3.return_value.get_paginator.return_value \
            .paginate.return_value = [{'Contents': []}]
        with pytest.raises(FileNotFoundError):
            download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    assert weights_ready(str(tmp_path)) is False


def test_clears_stale_partial_download_before_downloading(tmp_path):
    # A leftover file from an interrupted run (no marker present).
    (tmp_path / 'leftover.bin').touch()
    _run_download(tmp_path, ONE_FILE_PAGE)
    assert not (tmp_path / 'leftover.bin').exists()
    assert (tmp_path / 'model.safetensors').exists()


def test_skips_directory_placeholder_key(tmp_path):
    pages = [{'Contents': [
        {'Key': 'gemma4/test-variant/'},
        {'Key': 'gemma4/test-variant/model.safetensors'},
    ]}]
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        mock_s3.get_paginator.return_value.paginate.return_value = pages
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    assert mock_s3.download_file.call_count == 1


def test_preserves_nested_key_layout(tmp_path):
    pages = [{'Contents': [
        {'Key': 'gemma4/test-variant/subdir/nested.json'},
    ]}]
    with patch.dict(os.environ, S3_ENV), \
         patch('boto3.client') as mock_boto3:
        mock_s3 = mock_boto3.return_value
        mock_s3.get_paginator.return_value.paginate.return_value = pages
        mock_s3.download_file.side_effect = _make_file_on_download
        download_weights_backblaze('gemma4', 'test-variant', str(tmp_path))
    assert (tmp_path / 'subdir' / 'nested.json').exists()
