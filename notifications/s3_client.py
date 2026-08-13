import functools

import boto3
from botocore.config import Config
from django.conf import settings


@functools.lru_cache(maxsize=1)
def get_s3_client():
    return boto3.client(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        verify=settings.AWS_CERT_FILE_PATH,
        config=Config(signature_version='s3v4'),
    )


def _get_download_url(bucket: str, key: str) -> str:
    url = get_s3_client().generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=300,
    )
    if settings.ENVIRONMENT == 'dev':
        url = url.replace('scout-moto', settings.DEV_IP)
    return url


def get_detection_preview_download_url(img_key: str) -> str:
    return _get_download_url(settings.AWS_IMG_DETECTION_BUCKET, img_key)


def get_video_clip_download_url(clip_key: str) -> str:
    return _get_download_url(settings.AWS_VIDEO_CLIP_BUCKET, clip_key)
