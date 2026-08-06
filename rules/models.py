from django.db import models
from django.contrib.auth.models import AbstractUser

from users.models import User
from camera.models import Camera

class Rule(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Must be using PostgreSQL 18+ for the native UUID7 support.
    public_rule_id = models.UUIDField(editable=False, unique=True, db_default=models.Func(function="uuidv7"))
    # public_rule_id = models.UUIDField(editable=False, unique=True, default=uuid.uuid4)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    camera = models.ForeignKey(Camera, on_delete=models.CASCADE)
    rule = models.CharField(max_length=240)
    rule_nickname = models.CharField(max_length=240)
    is_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered = models.DateTimeField(null=True, blank=True)


    def __str__(self):
        return f'Rule: "{self.rule_nickname}" for user {self.owner.id} on camera {self.camera_id}.'
