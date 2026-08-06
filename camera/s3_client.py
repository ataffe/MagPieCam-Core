import functools
import boto3
from django.conf import settings
from botocore.config import Config
import logging

from camera.constants import UploadType

logger = logging.getLogger("Camera Serializer")

@functools.lru_cache(maxsize=1)
def get_s3_client():
    return boto3.client(
        's3',
        region_name=settings.AWS_REGION,
        endpoint_url=settings.AWS_ENDPOINT_URL,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(signature_version='s3v4'),
    )

def get_camera_preview_download_url(img_key):
    url = get_s3_client().generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': settings.AWS_IMG_PREVIEW_BUCKET,
                'Key': img_key},
        ExpiresIn=300,
    )
    if settings.ENVIRONMENT == 'dev':
        url = url.replace('scout-moto', settings.DEV_IP)
    return url

def get_upload_url(img_key: str, content_type: str, upload_type: str):
    s3_bucket_name = settings.AWS_IMG_DETECTION_BUCKET
    if upload_type == UploadType.CAMERA_PREVIEW:
        s3_bucket_name = settings.AWS_IMG_PREVIEW_BUCKET
    url = get_s3_client().generate_presigned_url(
            ClientMethod='put_object',
            Params={'Bucket': s3_bucket_name, 'Key': img_key, 'ContentType': content_type},
            ExpiresIn=300
        )
    if settings.ENVIRONMENT == 'dev':
        url = url.replace('scout-moto', settings.DEV_IP)
    return url