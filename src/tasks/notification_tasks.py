from datetime import datetime, timedelta
from sqlalchemy import select
from src.core.database import AsyncSessionLocal
from src.models.booking import Booking, BookingStatusEnum
from src.models.user import User
from src.tasks.celery_app import celery_app
from src.tasks.utils import async_task
import logging

logger = logging.getLogger(__name__)

@celery_app.task(
    bind = True,
    name = "src.tasks.notification_tasks.send_expiry_reminders",
    max_retries=2,
)
@async_task
async def send_expiry_reminders(self):
    logger.info("Task started: send_expiry_reminders")
    try:
        async with AsyncSessionLocal() as db:
            now = datetime.utcnow()
            threshold = now + timedelta(minutes=1)
            result = await db.execute(
                select(Booking,User)
                .join(User, Booking.user_id==User.id)
                .where(
                    Booking.status == BookingStatusEnum.RESERVED,
                    Booking.reserved_until.between(now, threshold),
                )
            )

            count = 0
            for booking, user in result.all():
                logger.info(
                    f"REMINDER: user = {user.email} booking={booking.id}"
                    f"expires at {booking.reserved_until}"
                )
                count +=1

            return {"sent": count}
    except Exception as exc:
        logger.exception("send_expiry_reminders failed")
        raise self.retry(exc=exc, countdown=30)

@celery_app.task(
    name="src.tasks.notification_tasks.send_booking_confirmation",
)
def send_booking_confirmation(user_email: str, booking_id: int, seat_info:str):
    logger.info(f'Sending confirmation to {user_email} for booking {booking_id}')
    return {"status": "sent", "to": user_email}