import logging
from sqlalchemy import update, select, delete
from src.core.database import AsyncSessionLocal
from src.models.booking import Booking, BookingStatusEnum
from src.models.seat import Seat
from datetime import datetime, timedelta
from src.services.cache_service import CacheService
from .celery_app import celery_app
from .utils import async_task
from src.core.redis_client import redis_client

logger = logging.getLogger(__name__)

@celery_app.task(
    bind = True,
    name = "src.tasks.cleanup_tasks.release_expired_seats",
    max_retries=3,
    default_retry_delay=30,
)
@async_task
async def release_expired_seats(self):
    """Асинхронно освобождает места, у которых истекло время резерва."""
    logger.info('Task started: release_expired_seats')
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            result = await db.execute(
                select(Booking).where(
                    Booking.status == BookingStatusEnum.RESERVED,
                    Booking.reserved_until < now,
                )
            )
            expired_bookings = result.scalars().all()
            if not expired_bookings:
                logger.info("No expired bookings found")
                return {"released": 0}
            affected_halls = set()
            for booking in expired_bookings:
                booking.status = BookingStatusEnum.EXPIRED
                await db.execute(
                    update(Seat)
                    .where(Seat.id == booking.seat_id)
                    .values(status='free')
                )
                seat_result = await db.execute(
                    select(Seat.hall_id).where(Seat.id == booking.seat_id)
                )
                hall_id = seat_result.scalar_one_or_none()
                if hall_id:
                    affected_halls.add(hall_id)

            await db.commit()

            for hall_id in affected_halls:
                await CacheService.invalidate_hall_seats(hall_id)

            logger.info(f"Released {len(expired_bookings)} seats", extra={
                "count": len(expired_bookings),
                "halls": list(affected_halls),
            })
            return {"released": len(expired_bookings)}
    except Exception as exc:
        logger.exception("Failed to release expired seats")
        raise self.retry(exc=exc, countdown = 2 ** self.request.retries)

@celery_app.task(
    bind=True,
    name="src.tasks.cleanup_tasks.cleanup_old_bookings",
    max_retries=3,
)
@async_task
async def cleanup_old_bookings(self):
    logger.info("Task started: cleanup_old_bookings")
    try:
        async with AsyncSessionLocal() as db:
            cutoff = datetime.utcnow()-timedelta(days=30)
            stmt = delete(Booking).where(
                Booking.created_at < cutoff,
                Booking.status.in_([
                    BookingStatusEnum.SOLD,
                    BookingStatusEnum.EXPIRED,
                    BookingStatusEnum.CANCELLED,
                    BookingStatusEnum.FAILED,
                ])
            )
            result = await db.execute(stmt)
            await db.commit()

            deleted = result.rowcount
            logger.info(f"Deleted {deleted} old bookings")
            return {"deleted": deleted}
    except Exception as exc:
        logger.exception("cleanup_old_bookings failed")
        raise self.retry(exc=exc, countdown=60)

@celery_app.task
def health_check():
    """Проверка, что Celery жив"""
    return{"status": "ok", "time":datetime.utcnow().isoformat()}