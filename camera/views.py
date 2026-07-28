import hashlib
import hmac
import logging
import secrets
import uuid

from rest_framework import status
from rest_framework import viewsets, permissions
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from camera.models import Camera
from camera.serializers import CameraSerializer, CameraRegistrationSerializer, ProvisionCameraSerializer, ClaimCameraSerializer
from camera.authentication import CameraTokenAuthentication, CameraJWTAuthentication
from camera.s3_client import get_detection_upload_url

ALLOWED_TYPES = {"image/jpeg", "image/png"}
logger = logging.getLogger('Camera API')

class CameraTokenExchangeView(APIView):
    authentication_classes = [CameraTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        camera = request.user
        token = AccessToken()
        token['public_camera_id'] = str(camera.public_camera_id)
        token['scope'] = 'camera'

        return Response({'access': str(token)}, status=status.HTTP_200_OK)

class CameraViewSet(viewsets.ModelViewSet):
    serializer_class = CameraSerializer
    lookup_field = 'public_camera_id'
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = Camera.objects.all()

        if user.is_staff and self.request.query_params.get('all') == 'true':
            return queryset

        return queryset.filter(owner=user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ProvisionCameraView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = ProvisionCameraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device_id = serializer.validated_data['device_id']

        if Camera.objects.filter(device_id=device_id).exists():
            return Response({'detail': 'Camera already provisioned'}, status=status.HTTP_409_CONFLICT)

        claim_secret = secrets.token_urlsafe(24)
        claim_token = f'{device_id}_{claim_secret}'
        claim_token_hash = hashlib.sha256(claim_token.encode('utf-8')).hexdigest()
        Camera.objects.create(
            device_id=device_id,
            claim_token_hash=claim_token_hash,
        )
        logger.info(f'Created new camera with device_id: {device_id}')
        return Response(
            {"claim_token": claim_token},
            status=status.HTTP_201_CREATED
        )

class CameraRegistrationView(APIView):
    permission_classes = [permissions.AllowAny]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = CameraRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        device_id = serializer.validated_data['device_id']
        try:
            camera = Camera.objects.get(device_id=device_id)
        except Camera.DoesNotExist:
            return Response({'detail': 'Camera does not exist'}, status=status.HTTP_404_NOT_FOUND)

        if camera.device_token_hash:
            return Response({'detail': 'Camera already registered'}, status=status.HTTP_400_BAD_REQUEST)

        # Double check the claim token for this camera.
        claim_token = serializer.validated_data['claim_token']
        claim_token_hash = hashlib.sha256(claim_token.encode('utf-8')).hexdigest()
        if not hmac.compare_digest(claim_token_hash, camera.claim_token_hash):
            logger.warning(f'Invalid claim token used for registration of device_id: {device_id}')
            return Response({'detail': 'Claim token does not match'}, status=status.HTTP_400_BAD_REQUEST)

        device_secret = secrets.token_urlsafe(24)
        device_token = f'{device_id}_{device_secret}'
        device_token_hash = hashlib.sha256(device_token.encode('utf-8')).hexdigest()
        camera.device_token_hash = device_token_hash
        camera.save()
        logger.info(f'Registered new camera with device_id: {device_id}')
        return Response({'device_token': device_token, 'public_camera_id': camera.public_camera_id},
                        status=status.HTTP_201_CREATED)

class CameraClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClaimCameraSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        claim_token = serializer.validated_data['claim_token']
        claim_token_hash = hashlib.sha256(claim_token.encode('utf-8')).hexdigest()
        device_id = claim_token.split('_', 1)[0]

        try:
            camera = Camera.objects.get(device_id=device_id)
        except Camera.DoesNotExist:
            return Response({'detail': 'Camera does not exist'}, status=status.HTTP_404_NOT_FOUND)

        if not hmac.compare_digest(claim_token_hash, camera.claim_token_hash):
            logger.warning(f'Invalid claim token used for claim of device_id: {device_id}')
            return Response({'detail': 'claim token does not match'}, status=status.HTTP_400_BAD_REQUEST)

        if camera.claimed:
            return Response({'detail': 'Camera already claimed'}, status=status.HTTP_400_BAD_REQUEST)

        camera.owner = request.user
        camera.location = serializer.validated_data['location']
        camera.claimed = True
        camera.claimed_at = timezone.now()
        camera.claim_token_hash = ''
        camera.save()
        logger.info(f'Claimed new camera with device_id: {device_id}')
        return Response({'public_camera_id': camera.public_camera_id}, status=status.HTTP_200_OK)


class PresignedImageUploadUrlView(APIView):
    authentication_classes = [CameraJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # User is really a Camera because CameraJWTAuthentication returns a camera instead of a user.
        # but django assigns the return value of authenticate to request.user
        camera = request.user
        public_camera_id = camera.public_camera_id
        logger.info(f'Generating a presigned url for camera: {public_camera_id}')
        content_type = request.data.get('content_type', 'image/jpeg')
        if content_type not in ALLOWED_TYPES:
            return Response({'detail': 'Unsupported content type'}, status=status.HTTP_400_BAD_REQUEST)

        image_format = 'jpeg' if content_type == 'image/jpeg' else 'png'
        upload_type = self.request.query_params.get('upload_type', None)
        if upload_type == 'DETECTION':
            img_key = f'detection/{public_camera_id}/{uuid.uuid4()}.{image_format}'
        elif upload_type == 'CAMERA_PREVIEW':
            # Preview images are always stored/served as .jpg (see
            # get_camera_preview_download_url), regardless of the uploaded
            # content type, since this key is a fixed, overwritten singleton.
            img_key = f'preview/{public_camera_id}/latest.jpg'
        else:
            return Response({'detail': 'Missing or Unsupported upload type'}, status=status.HTTP_400_BAD_REQUEST)

        url = get_detection_upload_url(img_key=img_key, content_type=content_type)
        return Response({'url': url, 'key': img_key, 'expires_in': 300})


class CameraPreviewTimeView(APIView):
    authentication_classes = [CameraJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        camera = request.user
        camera.preview_updated_at = timezone.now()
        camera.save()
        return Response(status=status.HTTP_200_OK)