from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from src.models.booking import Booking, BookingStatusEnum
from src.models.seat import Seat, SeatStatusEnum
from src.models.user import User
from src.services.cache_service import CacheService, logger


class BookingService:

    @staticmethod
    async def hold_seat(db: AsyncSession, seat_id: int, user_id: int):
        """
        Блокируем место.
        skip_locked=True означает: если этот ряд уже залочен другим запросом - игнорируем его.
        """
        user = await db.get(User, user_id)
        if not user:
            return None, "Пользователь не найден"
        # 1. Атомарное обновление с блокировкой строки в БД
        stmt = (
            select(Seat)
            .where(Seat.id == seat_id, Seat.status == SeatStatusEnum.FREE)
            .with_for_update(skip_locked=True)
        )
        result = await db.execute(stmt)
        seat = result.scalar_one_or_none()

        if not seat:
            return None, "Место уже занято"

        # 2. Создаем бронь
        now = datetime.utcnow()
        booking = Booking(
            user_id=user_id,
            seat_id=seat.id,
            status=BookingStatusEnum.RESERVED,
            reserved_until=now + timedelta(minutes=5),
            created_at=now
        )
        db.add(booking)


        # 3. Меняем статус места
        seat.status = SeatStatusEnum.RESERVED
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            return None, "Место занято"
        await db.refresh(booking)
        await CacheService.invalidate_hall_seats(seat.hall_id)
        return booking, None

    @staticmethod
    async def confirm_booking(db: AsyncSession, booking_id: int, idempotency_key: str, current_user: User ):
        """
        Покупка с идемпотентностью.
        """
        # Проверяем идемпотентность
        existing = await db.execute(
            select(Booking).where(Booking.idempotency_key == idempotency_key)
        )
        existing_booking = existing.scalar_one_or_none()

        if existing_booking is not None:
            if existing_booking.user_id !=current_user.id:
                return None, "Бронь была создана другим пользователем"
            return existing_booking, None

        booking = await db.get(Booking, booking_id)
        if not booking:
            return None, "Бронь не найдена"
        if booking.user_id != current_user.id:
            return None, "Бронь принадлежит другому пользователю"
        if booking.status != BookingStatusEnum.RESERVED:
            return None, f"Невозможно оплатить бронь со статусом {booking.status.value}"
        if booking.reserved_until < datetime.utcnow():
            await db.execute(
                update(Seat).where(Seat.id == booking.seat_id).values(status='free')
            )
            await BookingService.update_booking_status(db, booking_id, BookingStatusEnum.EXPIRED)
            return None, 'Время вышло'

        seat = await db.get(Seat, booking.seat_id)

        # Меняем статус на SOLD (оплачено)
        await BookingService.update_booking_status(db, booking_id, BookingStatusEnum.SOLD)
        booking.idempotency_key = idempotency_key

        result = await db.execute(select(User).where(User.id == booking.user_id))
        user = result.scalar_one_or_none()

        await db.commit()
        if user:
            from src.tasks.notification_tasks import send_booking_confirmation
            send_booking_confirmation.delay(user.email, booking.id, f"Место ID {booking.seat_id}")
        await db.refresh(booking)
        await CacheService.invalidate_hall_seats(seat.hall_id)
        return booking, None

    @staticmethod
    def can_transition(current_status: BookingStatusEnum, new_status: BookingStatusEnum) -> bool:
        """Конечный автомат: проверяем, можно ли перейти из статуса А в статус В."""
        allowed = {
            BookingStatusEnum.PENDING: [BookingStatusEnum.RESERVED, BookingStatusEnum.EXPIRED, BookingStatusEnum.CANCELLED],
            BookingStatusEnum.RESERVED: [BookingStatusEnum.SOLD, BookingStatusEnum.EXPIRED, BookingStatusEnum.CANCELLED, BookingStatusEnum.FAILED],
            BookingStatusEnum.SOLD: [],
            BookingStatusEnum.EXPIRED: [],
            BookingStatusEnum.CANCELLED: [],
            BookingStatusEnum.FAILED: [],
        }
        return new_status in allowed.get(current_status, [])

    @staticmethod
    async def update_booking_status(db: AsyncSession, booking_id: int, new_status: BookingStatusEnum):
        """Безопасное обновление статуса с проверкой."""
        booking = await db.get(Booking, booking_id)
        if not booking:
            raise ValueError ('Бронь не найдена')
        if not BookingService.can_transition(booking.status, new_status):
            raise ValueError(f'Невозможно перейти из статуса {booking.status} в {new_status}')
        if new_status in [BookingStatusEnum.SOLD, BookingStatusEnum.EXPIRED, BookingStatusEnum.CANCELLED, BookingStatusEnum.FAILED]:
            from src.models.seat import Seat
            await db.execute(
                update(Seat).where(Seat.id == booking.seat_id).values(status='free')
            )
            if new_status == BookingStatusEnum.SOLD:
                await db.execute(
                    update(Seat).where(Seat.id == booking.seat_id).values(status='sold')
                )
        booking.status = new_status
        await db.flush()
        return booking