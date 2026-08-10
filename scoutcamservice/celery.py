import logging
import os
from datetime import timedelta

from celery import Celery
from celery.signals import worker_process_init
from django.conf import settings

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scoutcamservice.settings')

logger = logging.getLogger('Celery')

app = Celery('scoutcamservice')

# Every CELERY_-prefixed Django setting becomes Celery config, so the broker URL
# and friends stay in settings.py with everything else.
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

app.conf.beat_schedule = {
    'sweep-readers': {
        'task': 'camera.tasks.sweep_readers',
        'schedule': timedelta(seconds=settings.STREAMING_READER_SWEEP_POLL_INTERVAL),
    },
}


@worker_process_init.connect
def preload_rules_model(**_kwargs):
    """Load and warm the rules model once, when a worker process boots.

    Fires in each prefork child right after fork, so the first real image task
    isn't the one that pays the multi-GB weight load and warm-up. Gated on an
    env var and set only on the ML worker (which runs at concurrency=1, so this
    loads exactly one copy) -- the lite/beat processes never touch the model
    stack. The import is deferred so those processes don't pull it in either.
    """
    if not os.environ.get('PRELOAD_RULES_MODEL'):
        return
    from events.processing import get_rules_model
    logger.info('Preloading rules model on worker process init...')
    get_rules_model()
    logger.info('Rules model preloaded.')
