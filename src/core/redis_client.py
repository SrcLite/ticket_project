import redis.asyncio as redis
from .config import settings
import logging

logger = logging.getLogger(__name__)

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True
)


async def check_redis_connection():
    try:
        await redis_client.ping()
        logger.info("Redis соединение установлено")
        return  True
    except Exception as e:
        logger.error(f"Redis соединение не установлено: {e}")
        return False
