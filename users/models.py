from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    # Must be using PostgreSQL 18+ for the native UUID7 support.
    public_user_id = models.UUIDField(editable=False, unique=True, db_default=models.Func(function="uuidv7"))
    # public_user_id = models.UUIDField(editable=False, unique=True, default=uuid.uuid4)
    email = models.EmailField(max_length=255, unique=True)
    apns_token = models.CharField(max_length=255, unique=True, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        db_table = 'users'

    def __str__(self):
        return self.username
