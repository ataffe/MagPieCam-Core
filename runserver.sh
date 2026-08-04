#!/bin/sh
python manage.py migrate
gunicorn --workers 3 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 scoutcamservice.asgi:application