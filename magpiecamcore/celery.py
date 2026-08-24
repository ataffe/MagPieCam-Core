import logging
import os
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer

from celery import Celery
from celery.signals import worker_init, worker_process_init, worker_process_shutdown
from django.conf import settings
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'magpiecamcore.settings')

logger = logging.getLogger('Celery')

app = Celery('magpiecamcore')

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

    Fires in each prefork child right after fork, and downloads the models weights,
    (which takes a few minutes) if the hosted version of the model is used. If the
    API version is used it just creates an instance of the rules model which takes
    seconds.
    """
    if not os.environ.get('PRELOAD_RULES_MODEL'):
        return
    from events.processing import get_rules_model
    logger.info('Preloading rules model on worker process init...')
    get_rules_model()
    logger.info('Rules model preloaded.')

class _MultiProcessMetricsHandler(BaseHTTPRequestHandler):
    """Aggregates the counters from every forked child.
    """

    def do_GET(self):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        output = generate_latest(registry)
        self.send_response(200)
        self.send_header('Content-Type', CONTENT_TYPE_LATEST)
        self.end_headers()
        self.wfile.write(output)

    def log_message(self, *_args):
        pass


@worker_init.connect
def start_metrics_server(**_kwargs):
    """Fires once in the master process, before any pool child is forked.
    """
    multiproc_dir = os.environ.get('PROMETHEUS_MULTIPROC_DIR')
    if not multiproc_dir:
        logger.warning('PROMETHEUS_MULTIPROC_DIR not set; skipping metrics export.')
        return

    os.makedirs(multiproc_dir, exist_ok=True)
    for name in os.listdir(multiproc_dir):
        os.remove(os.path.join(multiproc_dir, name))

    # Added bandit suppression because this runs in a docker container
    httpd = HTTPServer(('0.0.0.0', settings.CELERY_WORKER_METRICS_PORT), _MultiProcessMetricsHandler) # nosec B104
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


@worker_process_shutdown.connect
def mark_worker_process_dead(pid, **_kwargs):
    if os.environ.get('PROMETHEUS_MULTIPROC_DIR'):
        multiprocess.mark_process_dead(pid)
