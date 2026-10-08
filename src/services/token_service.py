from datetime import datetime, timezone
from src.core.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)

class TokenService:
    BLACKLIST_PREFIX = 'blacklist:token'

    @staticmethod
    def _key(jti: str) -> str:
        return f"{TokenService.BLACKLIST_PREFIX}:{jti}"

    @staticmethod
    def _ttl(exp:int)->int:
        return int(exp - datetime.now(timezone.utc).timestamp())

    @classmethod
    async def blacklist(cls, jti: str, exp: int) -> bool:
        ttl = cls._ttl(exp)
        if ttl <= 0:
            return True
        await redis_client.setex(cls._key(jti), ttl, '1')
        return True

    @classmethod
    async def consume_once(cls, jti: str, exp: int)->bool:
        ttl = cls._ttl(exp)
        if ttl <= 0:
            return False
        return bool(await redis_client.set(cls._key(jti), '1', nx=True, ex=ttl))

    @classmethod
    async def is_blacklisted(cls, jti: str)->bool:
        return bool(await redis_client.exists(cls._key(jti)))
