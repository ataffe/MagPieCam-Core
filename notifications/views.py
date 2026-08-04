from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from notifications.models import Notification
from notifications.serializers import NotificationSerializer
from camera.models import Camera

class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "public_notification_id"

    def get_queryset(self):
        camera = get_object_or_404(
            Camera,
            public_camera_id=self.kwargs["public_camera_id_public_camera_id"],
            owner=self.request.user,
        )
        return (
            Notification.objects
            .filter(camera=camera)
            .select_related("rule")
            .order_by("-created_at")
        )
