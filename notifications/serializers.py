from rest_framework import serializers

from notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    # Expose the stable public UUIDs rather than the internal DB primary keys.
    public_camera_id = serializers.UUIDField(
        source="camera.public_camera_id", read_only=True)
    rule_nickname = serializers.CharField(
        source="rule.rule_nickname", read_only=True
    )

    class Meta:
        model = Notification
        fields = [
            "public_notification_id",
            "public_camera_id",
            "rule_nickname",
            "created_at",
        ]
