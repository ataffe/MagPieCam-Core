# myapp/tasks.py
#
# Poll-only stream stopping, as a scheduled Celery task.
#
# Celery Beat fires sweep_readers() every POLL_INTERVAL seconds; a Celery worker
# runs it. It reads reader counts straight from MediaMTX (the authoritative
# observer of who's connected, including clients that vanished ungracefully),
# and stops any camera that's been empty past the grace window.
#
# NOTE: Celery tasks are SYNCHRONOUS, so everything here uses sync clients
# (redis, httpx sync) — no async/await, unlike the long-poll view.

import time

import httpx
import redis
from celery import shared_task
from camera.streaming_control import channel, streaming_state_key, empty_key
from django.conf import settings

redis_client = redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

def publish_stop(path: str) -> None:
    # clear camera state, then wake the Pi's command channel.
    redis_client.delete(streaming_state_key(path))
    redis_client.publish(channel(path), "stop")

def evaluate_camera_stream(public_camera_id: str, reader_count: int) -> None:
    """The stop decision. Idempotent — safe to run every sweep."""
    now = time.time()

    if reader_count > 0:
        redis_client.delete(empty_key(public_camera_id))   # someone's watching; cancel any pending stop
        return

    empty_since = redis_client.get(empty_key(public_camera_id))
    if empty_since is None:
        redis_client.set(empty_key(public_camera_id), now)  # start the grace clock
        return

    # Wait for n seconds before actually stopping the stream in case a user
    # reconnects
    if now - float(empty_since) >= settings.STREAMING_READER_SWEEP_EMPTY_GRACE_PERIOD:
        publish_stop(public_camera_id)
        redis_client.delete(empty_key(public_camera_id))


@shared_task
def sweep_readers() -> None:
    # This is a periodic task. If a sweep ever runs long, this lock stops
    # the next one from overlapping it. blocking=False => just skip this tick.
    # The timeout auto-releases the lock if a worker dies mid-sweep.
    lock = redis_client.lock("lock:sweep_readers", timeout=settings.STREAMING_READER_SWEEP_POLL_INTERVAL - 1)
    if not lock.acquire(blocking=False):
        return

    try:
        resp = httpx.get(f"{settings.MEDIAMTX_API_URL}/v3/paths/list", timeout=5.0)
        resp.raise_for_status()
        for item in resp.json().get("items", []):
            if not item.get("ready"):          # only paths with a live publisher
                continue
            # readers counts WebRTC/RTSP/RTMP viewers, NOT HLS (which shows one
            # muxer.
            public_camera_id = item.get("name", "")
            num_readers = len(item.get("readers", []))
            evaluate_camera_stream(public_camera_id, num_readers)
    finally:
        try:
            lock.release()
        except redis.exceptions.LockError:
            pass  # already expired via timeout; nothing to release