import hashlib
import logging
from rest_framework import authentication, exceptions
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed, TokenError
from asgiref.sync import sync_to_async
from .models import Camera

logger = logging.getLogger('Camera Auth API')

jwt_auth = JWTAuthentication()

class CameraTokenAuthentication(authentication.BaseAuthentication):
    keyword = b'device'  # matches "Authorization: Device <token>"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).split()

        # Not our scheme? Return None so DRF can try the next authenticator.
        if not header or header[0].lower() != self.keyword:
            return None
        if len(header) == 1:
            logger.error('Device id not found.')
            raise exceptions.AuthenticationFailed('No device token provided.')
        if len(header) > 2:
            logger.error('Device token not found.')
            raise exceptions.AuthenticationFailed('Device token header is malformed.')

        device_token = header[1].decode()
        token_hash = hashlib.sha256(device_token.encode('utf-8')).hexdigest()

        try:
            camera = Camera.objects.get(
                device_token_hash=token_hash
            )
        except Camera.DoesNotExist:
            logger.error('Camera with device_token does not exist.')
            raise exceptions.AuthenticationFailed('Invalid device token.')

        if camera.revoked:
            logger.error('Camera has been revoked.')
            raise exceptions.AuthenticationFailed('Device has been revoked.')

        # DRF expects (user, auth). Here the "user" is the camera.
        return camera, device_token

    def authenticate_header(self, request):
        # Without this, DRF can't issue a WWW-Authenticate challenge and
        # silently downgrades auth failures from 401 to 403.
        return 'Device'

class CameraJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        if validated_token.get('scope') != 'camera':
            logger.error('Camera JWT authentication failed. Invalid scope.')
            raise InvalidToken('Not a camera token.')
        public_camera_id = validated_token.get('public_camera_id')
        if not public_camera_id:
            logger.error('Camera JWT authentication failed. public_camera_id is not found.')
            raise InvalidToken('Token is missing camera id.')
        try:
            camera = Camera.objects.get(public_camera_id=public_camera_id)
        except Camera.DoesNotExist:
            logger.error('Camera with public_camera_id does not exist.')
            raise AuthenticationFailed('Camera for this token does not exist.')

        if camera.revoked:
            logger.error('Camera has been revoked.')
            raise AuthenticationFailed('Camera has been revoked.')

        return camera

async def authenticate_jwt_async(request):
    auth_header = request.headers.get('Authorization', "")
    if not auth_header.startswith('Bearer '):
        return None

    raw_token = auth_header[len('Bearer '):]
    try:
        validated_token = await sync_to_async(jwt_auth.get_validated_token)(raw_token)
        public_camera_id = validated_token.get('public_camera_id')
        await Camera.objects.aget(public_camera_id=public_camera_id, revoked=False)
    except (TokenError, AuthenticationFailed) as e:
        return None
    except Camera.DoesNotExist:
        logger.warning('Camera with public_camera_id does not exist.')
        return None

    return public_camera_id



