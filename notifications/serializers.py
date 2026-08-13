from rest_framework import serializers

from notifications.models import Notification
from notifications.s3_client import (
    get_detection_preview_download_url, get_video_clip_download_url,
)


class NotificationSerializer(serializers.ModelSerializer):
    # Expose the stable public UUIDs rather than the internal DB primary keys.
    public_camera_id = serializers.UUIDField(
        source="camera.public_camera_id", read_only=True)
    detection_preview_url = serializers.SerializerMethodField()
    video_clip_url = serializers.SerializerMethodField()

    def get_detection_preview_url(self, notification: Notification) -> str:
        # Don't generate a presigned URL for a key that was never recorded.
        if not notification.detection_image_key:
            return None
        return get_detection_preview_download_url(notification.detection_image_key)

    def get_video_clip_url(self, notification: Notification) -> str:
        # Null until the clip has actually landed in S3, so the app can tell
        # "no clip yet" apart from a URL that would 404.
        if not notification.video_clip_key:
            return None
        return get_video_clip_download_url(notification.video_clip_key)

    class Meta:
        model = Notification
        fields = [
            "public_notification_id",
            "public_camera_id",
            "rule_nicknames",
            "video_clip_key",
            "detection_preview_url",
            "video_clip_url",
            "created_at",
        ]


class ClearNotificationsRequestSerializer(serializers.Serializer):
    public_notification_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False)


class ClearNotificationsResponseSerializer(serializers.Serializer):
    cleared_count = serializers.IntegerField()
