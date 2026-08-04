import boto3
import os
from pathlib import Path
import logging

logger = logging.getLogger("Weights Util")


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
    paginator = s3_client.get_paginator('list_objects_v2')
    prefix = f'{model_name}/{model_variant_name}/'
    for page in paginator.paginate(Bucket=s3_bucket, Prefix=prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            filename = Path(key).name
            logger.info(f'Downloading {filename}')
            dest = f'{download_dir}/{filename}'
            s3_client.download_file(s3_bucket, key, dest)

    if not any(download_dir.iterdir()):
        raise FileNotFoundError(f'No files found in {download_dir}')
