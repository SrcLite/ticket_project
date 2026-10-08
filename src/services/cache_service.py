import json
import logging
from typing import Optional, Any
from src.core.redis_client import redis_client

logger = logging.getLogger(__name__)

class CacheService:
    """
    Сервис для работы с Redis.
    Ключи формируются по шаблону: {namespace}:{id}
    """

    SEATS_CACHE_TTL = 5 #5 секунд
    HALL_SEATS_PREFIX = "hall:seats"

    @staticmethod
    def _make_key(namespace: str, identifier: Any) -> str:
        """Формирует ключ для Redis."""
        return f"{namespace}:{identifier}"

    @classmethod
    async def get(cls, namespace: str, identifier: Any) -> Optional[Any]:
        """Получить значение из кэша. Возвращает None, если нет."""
        key = cls._make_key(namespace, identifier)
        try:
            data = await redis_client.get(key)
            if data:
                logger.info(f"Cache HIT: {key}")
                return json.loads(data)
            logger.info(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Redis GEt error for {key}: {e}")
            return None #Не роняем приложение из-за Redis

    @classmethod
    async def set(cls, namespace: str, identifier: Any, value: Any, ttl: int=60) -> bool:
        """Записать значение в кэш с TTL."""
        key = cls._make_key(namespace, identifier)
        try:
            await redis_client.setex(key, ttl, json.dumps(value, default=str))
            logger.info(f"Cache SET: {key} (TTL={ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis SET error for {key}: {e}")
            return False

    @classmethod
    async def delete(cls, namespace: str, identifier: Any) -> bool:
        """Удалить ключ из кэша."""
        key = cls._make_key(namespace, identifier)
        try:
            await redis_client.delete(key)
            logger.info(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error for {key}: {e}")
            return False


    @staticmethod
    async def delete_pattern(cls, pattern: str) -> int:
        """Удалить все ключи по паттерну."""
        deleted = 0
        try:
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)
                deleted += 1
            logger.info(f"Cache DELETE PATTERN: {pattern} (deleted {deleted})")
            return deleted
        except Exception as e:
            logger.error(f"Redis SCAN error for {pattern}: {e}")
            return 0

    #СПЕЦМЕТОДЫ

    @classmethod
    async def get_hall_seats(cls, hall_id: int) -> Optional[list]:
        """Получить список мест зала из кэша."""
        return await cls.get(cls.HALL_SEATS_PREFIX, hall_id)

    @classmethod
    async def set_hall_seats(cls, hall_id: int, seats: list) -> bool:
        """Записать список мест в зале в кэш"""
        return await cls.set(
            cls.HALL_SEATS_PREFIX,
            hall_id,
            seats,
            ttl=cls.SEATS_CACHE_TTL
        )

    @classmethod
    async def invalidate_hall_seats(cls, hall_id: int) -> bool:
        """Инвалидировать кэш мест зала."""
        return await cls.delete(
            cls.HALL_SEATS_PREFIX,
            hall_id)