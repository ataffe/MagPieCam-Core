import io
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

import boto3
from PIL import Image
from botocore.config import Config
from django.conf import settings

from events.interfaces import ImageStorageClient, ParsedMessage

logger = logging.getLogger('S3 Client')


def s3_config_from_settings() -> dict:
    return {
        'endpoint_url': settings.AWS_ENDPOINT_URL,
        'region_name': settings.AWS_REGION,
        'aws_access_key_id': settings.AWS_ACCESS_KEY_ID,
        'aws_secret_access_key': settings.AWS_SECRET_ACCESS_KEY,
        'aws_cert_file': settings.AWS_CERT_FILE_PATH,
    }


class S3ImageStorageClient(ImageStorageClient):
    def __init__(self, config_dict=None, num_workers=10):
        config_dict = config_dict or s3_config_from_settings()
        # A single client handles both object downloads and presigned URLs --
        # the resource API has no presigned-URL support, so there's no reason
        # to keep two separate boto3 handles open.
        self.s3_client = boto3.client(
            's3',
            endpoint_url=config_dict['endpoint_url'],
            region_name=config_dict['region_name'],
            aws_access_key_id=config_dict['aws_access_key_id'],
            aws_secret_access_key=config_dict['aws_secret_access_key'],
            verify=config_dict['aws_cert_file'],
            config=Config(signature_version='s3v4')
        )
        self.num_workers = num_workers

    def download_image(self, bucket: str, key: str) -> Image.Image:
        """Fetch a single object. Raises errors rather than returning None so a Celery
        task can fail loudly and let the message become visible again."""
        try:
            response = self.s3_client.get_object(Bucket=bucket, Key=key)
        except self.s3_client.exceptions.NoSuchKey as e:
            logger.exception(f"No image found for key {key}")
            raise e

        image = Image.open(io.BytesIO(response['Body'].read()))
        image.load()
        return image

    def _fetch_image(self, parsed_message: ParsedMessage) -> Tuple[str, Image.Image] | None:
        try:
            image = self.download_image(parsed_message.bucket, parsed_message.key)
            return parsed_message.public_camera_id, image
        except Exception as e:
            logger.error(f'Error while downloading image. Key:{parsed_message.key} | Error: {e}')
        return None

    def download_images(self, parsed_messages: List[ParsedMessage]) -> Dict[str, List[Image.Image]]:
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            results = executor.map(self._fetch_image, parsed_messages)

        images_by_camera_id_dict = defaultdict(list)
        failed_count = 0
        for result in results:
            if result is None:
                failed_count += 1
                continue
            public_camera_id, image = result
            images_by_camera_id_dict[public_camera_id].append(image)

        if failed_count:
            logger.warning(f'{failed_count}/{len(parsed_messages)} images failed to download')

        return images_by_camera_id_dict

    def get_image_download_url(self, img_bucket: str, img_key: str) -> str:
        url = self.s3_client.generate_presigned_url(
            ClientMethod='get_object',
            Params={'Bucket': img_bucket, 'Key': img_key},
            ExpiresIn=300
        )
        if settings.ENVIRONMENT == 'dev':
            url = url.replace('scout-moto', settings.DEV_IP)
        return url

