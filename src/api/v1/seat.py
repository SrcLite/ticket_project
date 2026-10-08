from fastapi import APIRouter, Depends, HTTPException, status
from redis import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_current_admin
from src.core.database import get_db
from src.core.redis_client import redis_client
from src.models.seat import Seat
from src.models.hall import Hall
from src.models.user import User
from src.services.cache_service import CacheService
from typing import List

router = APIRouter()

@router.get("/halls/{hall_id}/seats", response_model=List[dict])
async def get_hall_seats(
        hall_id: int,
        db: AsyncSession = Depends(get_db)
):
    cached_seats = await CacheService.get_hall_seats(hall_id)
    if cached_seats is not None:
        return cached_seats

    hall = await db.get(Hall, hall_id)
    if not hall:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Зал {hall_id} не найден")

    result = await db.execute(select(Seat).where(Seat.hall_id == hall_id))

    seats_data = [
        {
            "id": seat.id,
            "status": seat.status.value
        }
        for seat in result.scalars().all()
    ]

    await CacheService.set_hall_seats(hall_id, seats_data)
    return seats_data

@router.get("/cache/stats")
async def cache_stats(current_user: User = Depends(get_current_admin)):
    """Статистика использования Redis"""
    try:
        info = await redis_client.info("stats")
        keys = await redis_client.dbsize()
    except RedisError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Redis недоступна")
    return {
        "total_keys": keys,
        "hits": info.get("keyspace_hits", 0),
        "misses": info.get("keyspace_misses", 0),
        "hit_rate": round(
            info.get("keyspace_hits", 0) /
            max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1), 1) * 100, 2
        )
    }