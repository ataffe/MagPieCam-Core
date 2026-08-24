#!/bin/sh
python manage.py migrate

# Reset the multiprocess metrics dir so a restarted container
# doesn't mix mmap files from a previous run's.
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -rf "$PROMETHEUS_MULTIPROC_DIR"
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

gunicorn --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 -c gunicorn.conf.py magpiecamcore.asgi:application