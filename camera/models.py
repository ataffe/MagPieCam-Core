from django.db import models

from users.models import User

class Camera(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Must be using PostgreSQL 18+ for the native UUID7 support.
    public_camera_id = models.UUIDField(editable=False, unique=True, db_default=models.Func(function="uuidv7"))
    # Null until the camera is claimed by a user.
    owner = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    location = models.CharField(max_length=100)
    # Null for cameras that weren't created through hardware provisioning.
    device_id = models.CharField(max_length=16, unique=True, editable=False, null=True, blank=True)
    # SHA-256 hex digest of device token which is scout_<serial_num>_<secret>.
    device_token_hash = models.CharField(max_length=64)
    # SHA-256 hex digest of the one-time use claim secret.
    claim_token_hash = models.CharField(max_length=64)
    claimed = models.BooleanField(default=False)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    claimed_at = models.DateTimeField(blank=True, null=True)
    preview_updated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                        models.Q(claimed=False)
                        | models.Q(claimed=True, owner__isnull=False)
                ),
                name="claimed_camera_requires_owner",
            ),
        ]

    @property
    def is_authenticated(self):
        return True

    def __str__(self):
        owner_id = self.owner_id if self.owner_id is not None else 'unclaimed'
        return f'Camera(serial_num: {self.device_id}) at location {self.location} for user {owner_id}.'