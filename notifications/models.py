from django.contrib.postgres.fields import ArrayField
from django.db import models
from django_prometheus.models import ExportModelOperationsMixin

from camera.models import Camera
from rules.models import Rule


class Notification(ExportModelOperationsMixin('Notification'), models.Model):
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
    # One detection image is evaluated against every rule on the camera, and
    # every rule that fires shares that image and its clip -- so they're
    # bundled into a single notification rather than one notification each.
    rules = models.ManyToManyField(
        Rule,
        blank=True,
        related_name='notifications',
    )
    # Denormalized copy of the nicknames: deleting a rule drops its row from
    # the m2m table, this keeps the notification readable afterwards.
    rule_nicknames = ArrayField(models.CharField(max_length=240), default=list)
    detection_image_key = models.CharField(null=True, blank=True)
    # Stays null until the clip actually lands in S3
    video_clip_key = models.CharField(null=True, blank=True)
    visible = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

