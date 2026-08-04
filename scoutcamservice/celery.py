import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scoutcamservice.settings')

app = Celery('scoutcamservice')

# Every CELERY_-prefixed Django setting becomes Celery config, so the broker URL
# and friends stay in settings.py with everything else.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Picks up tasks.py in each installed app.
app.autodiscover_tasks()
