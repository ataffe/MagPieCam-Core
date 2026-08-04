# Ensures the Celery app is created when Django starts, so @shared_task in the
# installed apps binds to it.
from .celery import app as celery_app

__all__ = ('celery_app',)
