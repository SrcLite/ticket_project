from datetime import datetime, timedelta
from sqlalchemy import select, func
from src.core.database import AsyncSessionLocal
from src.core.redis_client import redis_client
from src.models.booking import Booking, BookingStatusEnum
from src.tasks.celery_app import celery_app
from src.tasks.utils import async_task
import json
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="src.tasks.analytics_tasks.aggregate_hourly_stats", bind=True, max_retries=3, default_retry_delay=30)
@async_task
async def aggregate_hourly_stats(self):
        """Считает статистику продаж за час и кидает в Redis"""
        try:
            logger.info("Task started: aggregate_hourly_stats")
            async with AsyncSessionLocal() as db:
                since = datetime.utcnow() - timedelta(hours=1)

                sold_count_result = await db.execute(
                    select(func.count(Booking.id))
                    .where(
                        Booking.status == BookingStatusEnum.SOLD,
                        Booking.updated_at >= since,
                    )
                )
                sold_count = sold_count_result.scalar() or 0
                expired_result = await db.execute(
                    select(func.count(Booking.id))
                    .where(
                        Booking.status == BookingStatusEnum.EXPIRED,
                        Booking.updated_at >= since,
                    )
                )
                expired_count = expired_result.scalar() or 0

                stats = {
                    "period": "last_hour",
                    "sold": sold_count,
                    "expired": expired_count,
                    "conversion_rate": round(
                        sold_count / max(sold_count + expired_count, 1)*100, 2
                    ),
                    "computed_at": datetime.utcnow().isoformat(),
                }
                await redis_client.setex("stats:hourly", 7200, json.dumps(stats))
                logger.info(f"Stats aggregated: {stats}")
                return stats
        except Exception as exc:
            logger.exception("aggregate_hourly_stats failed")
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)