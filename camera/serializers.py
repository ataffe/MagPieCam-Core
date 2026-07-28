from rest_framework import serializers

from camera.models import Camera
from camera.s3_client import get_camera_preview_download_url

class CameraSerializer(serializers.ModelSerializer):
    public_camera_id = serializers.UUIDField(read_only=True)
    owner = serializers.StringRelatedField(read_only=True)
    camera_preview_url = serializers.SerializerMethodField()

    def get_camera_preview_url(self, camera):
        # Don't generate a presigned URL for a key that was never uploaded.
        if not camera.preview_updated_at:
            return None
        return get_camera_preview_download_url(f'preview/{camera.public_camera_id}/latest.jpg')

    class Meta:
        model = Camera
        fields = '__all__'
        read_only_fields = [
            'public_camera_id', 'owner', 'created_at', 'updated_at',
            'device_id', 'device_token_hash', 'claim_token_hash',
            'claimed', 'revoked', 'claimed_at', 'preview_updated_at',
        ]

class CameraRegistrationSerializer(serializers.Serializer):
    device_id = serializers.CharField(
        max_length=16,
        min_length=16,
        allow_blank=False,
        trim_whitespace=True)
    claim_token = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
        allow_blank=False)

class ProvisionCameraSerializer(serializers.Serializer):
    device_id = serializers.CharField(
        max_length=16,
        min_length=16,
        allow_blank=False,
        trim_whitespace=True)

class ClaimCameraSerializer(serializers.Serializer):
    claim_token = serializers.CharField(
        max_length=128,
        trim_whitespace=True,
        allow_blank=False
    )
    location = serializers.CharField(
        max_length=50,
        allow_blank=False,
        trim_whitespace=True,
    )