from django.db import models

from camera.models import Camera
from rules.models import Rule


class Notification(models.Model):
    class Meta:
        indexes = [
            models.Index(fields=["camera", "-public_notification_id"]),
        ]
        ordering = ["-public_notification_id"]
    id = models.BigAutoField(primary_key=True)
    public_notification_id = models.UUIDField(
        editable=False,
        unique=True,
        db_default=models.Func(function="uuidv7"))
    camera = models.ForeignKey(
        Camera,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    rule = models.ForeignKey(
        Rule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications'
    )
    created_at = models.DateTimeField(auto_now_add=True)

