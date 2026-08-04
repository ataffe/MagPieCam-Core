import redis.asyncio as redis
from django.conf import settings
import logging

logger = logging.getLogger("Redis Client")
def get_redis_client():
    return redis.Redis(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True)

def channel(public_camera_id: str) -> str:
    return f"camera:{public_camera_id}:commands"

def streaming_state_key(public_camera_id: str) -> str:
    return f"camera:{public_camera_id}:streaming_state"

def empty_key(public_camera_id: str) -> str:
    return f"camera:{public_camera_id}:empty_since"

async def publish_command(public_camera_id, command: str):
    async with get_redis_client() as redis_client:
        if command == "start":
            logger.info(f"starting stream for camera {public_camera_id}")
            await redis_client.setex(streaming_state_key(public_camera_id), settings.STREAMING_STATE_KEY_TTL, "stream")
        elif command == "stop":
            logger.info(f"stopping stream for camera {public_camera_id}")
            await redis_client.delete(streaming_state_key(public_camera_id))

        await redis_client.publish(channel(public_camera_id), command)

