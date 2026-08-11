from django.conf import settings
import logging
from datetime import datetime, timezone
import ssl
import jwt
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
from enum import StrEnum
from cachetools import TTLCache, cached

from notifications.models import Notification

logger = logging.getLogger("Apple Push Notification Client")

ssl_context = ssl.create_default_context()
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

cache_storage = TTLCache(maxsize=1, ttl=settings.APNS_JWT_STALE_TIME_SECONDS)


class APNServiceError(Exception):
    pass


class ApnsPushType(StrEnum):
    ALERT = 'alert'
    BACKGROUND = 'background'


@cached(cache=cache_storage)
def refresh_jwt():
    with open(settings.APNS_PRIVATE_KEY_PATH, 'rb') as f:
        private_key = f.read()

    if not private_key:
        logger.error("No private key found, please set APNS_PRIVATE_KEY_PATH")
        raise FileNotFoundError("Private key not found.")

    key_id = settings.APNS_KEY_ID
    issuer_id = settings.APNS_TEAM_ID
    issued_at = datetime.now(timezone.utc)

    return jwt.encode(
        {
            "iss": issuer_id,
            "iat": issued_at,
        },
        private_key,
        algorithm="ES256",
        headers={
            "alg": "ES256",
            "kid": key_id,
        })


@retry(
    stop=stop_after_attempt(settings.APNS_CLIENT_RETRIES),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(APNServiceError),
    reraise=True)
def _post_notification(headers: dict, body: dict, url: str) -> httpx.Response:
    with httpx.Client(http2=True, verify=ssl_context) as client:
        response = client.post(url, headers=headers, json=body)

    if response.status_code == 500:
        raise APNServiceError(f"APNs returned a 500 for topic {headers.get('apns-topic')}")

    return response


def send_notification(notification: Notification, preview_img_url: str) -> bool:
    try:
        access_token = refresh_jwt()
    except Exception as e:
        logger.error(f" Unable to refresh JWT: {e}")
        return False

    device_id = notification.camera.owner.apns_device_id
    if not device_id:
        logger.error(" Unable to send notification, no device found for user.")
        return False

    headers = {
        'authorization': f'bearer {access_token}',
        'apns-topic': settings.APNS_APP_BUNDLE_ID,
        'apns-push-type': ApnsPushType.ALERT,
        'apns-priority': str(settings.APNS_PRIORITY),
    }

    rule = notification.rule
    camera = notification.camera
    body = {
        "aps": {
            "mutable-content": 1,
            "alert": {
                "title": f"ScoutCam Rule Triggered!",
                "body": f"{rule.rule} has been seen in the {camera.location}".capitalize()
            }
        },
        "detection-image-url": preview_img_url,
    }
    url = f"{settings.APNS_URL}/3/device/{device_id}"

    try:
        response = _post_notification(headers, body, url)
    except Exception as ex:
        logger.error(f" Unable to send notification, error: {ex}")
        return False

    if response.status_code != 200:
        error_response = response.json() if response.content else {}
        logger.error(f" Unable to send notification, status code: {response.status_code}, error: {error_response}")
        return False

    apns_id = str(response.headers.get('apns-unique-id', "")).lower()
    if apns_id:
        logger.info(f" Successfully sent notification id: {apns_id}")
    else:
        logger.warning(f" Successfully sent notification id but no id was returned.")

    return True
