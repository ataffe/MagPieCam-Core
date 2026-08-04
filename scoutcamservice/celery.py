import os
from datetime import timedelta
from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "scoutcamservice.settings")
app = Celery("scoutcam")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "sweep-readers": {
        "task": "camera.tasks.sweep_readers",
        "schedule": timedelta(seconds=settings.STREAMING_READER_SWEEP_POLL_INTERVAL),
    },
}