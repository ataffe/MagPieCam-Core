import boto3
import os
import shutil
from pathlib import Path
import logging

logger = logging.getLogger("Weights Util")

# Written only after every object has finished downloading. Its presence is the
# signal that the weights dir is complete and safe to load -- an interrupted
# download leaves files but no marker, so the next run knows to start over.
_WEIGHTS_READY_MARKER = ".weights_ready"


def weights_ready(download_dir: str) -> bool:
    """True only if a previous download finished cleanly (marker present)."""
    return (Path(download_dir) / _WEIGHTS_READY_MARKER).exists()


def _clear_dir_contents(directory: Path) -> None:
    """Empty a directory without removing the directory itself.

    The weights dir is a mount point (named volume), so rmtree on it would fail
    trying to unlink the mount -- clear its contents instead.
    """
    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def download_weights_backblaze(
        model_name: str, model_variant_name: str,
        download_dir: str) -> None:
    logger.info(f"Downloading weights backblaze for {model_name}. This might take a while...")
    s3_bucket = os.environ.get('OBJ_STORE_ML_BUCKET', None)
    endpoint_url = os.environ.get('OBJ_STORE_ENDPOINT_URL', None)
    aws_access_key_id = os.environ.get('OBJ_STORE_ACCESS_KEY_ID', None)
    aws_secret_access_key = os.environ.get('OBJ_STORE_SECRET_ACCESS_KEY', None)

    s3_client = boto3.client(
        service_name='s3',
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
    )
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    # We only get here when the weights aren't ready, so anything already in the
    # dir is a stale partial download -- wipe it before starting clean.
    _clear_dir_contents(download_dir)

    paginator = s3_client.get_paginator('list_objects_v2')
    prefix = f'{model_name}/{model_variant_name}/'
    downloaded_any = False
    for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            # Skip the prefix's own "directory" placeholder object, if any.
            if key.endswith('/'):
                continue
            # Preserve any nested layout under the prefix rather than flattening.
            rel = Path(key).relative_to(prefix)
            dest = download_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f'Downloading {rel}')
            s3_client.download_file(s3_bucket, key, str(dest))
            downloaded_any = True

    if not downloaded_any:
        raise FileNotFoundError(
            f'No objects found under s3://{s3_bucket}/{prefix}')

    # Marker last: only now is the set known to be complete.
    (download_dir / _WEIGHTS_READY_MARKER).touch()
