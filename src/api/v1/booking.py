from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_current_user
from src.core.database import get_db
from src.models.user import User
from src.services.booking_service import BookingService

router = APIRouter()

@router.post("/hold/{seat_id}")
async def hold_seat(
        seat_id: int,
        db:AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
    """
    Забронировать место на 5 минут
    """
    booking, error = await BookingService.hold_seat(db, seat_id, current_user.id)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {
        "status": "success",
        "booking_id": booking.id,
        "reserved_until": booking.reserved_until.isoformat(),
        "message": f"Место {seat_id} забронировано до {booking.reserved_until}"
    }

@router.post("/confirm/{booking_id}")
async def confirm_booking(
        booking_id: int,
        idempotency_key: str = Header(..., alias="Idempotency-Key"),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
    ):
    """
    Оплатить бронь.
    """
    booking, error = await BookingService.confirm_booking(db, booking_id, idempotency_key, current_user)
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {
        "status": "success",
        "booking_id": booking.id,
        "seat_id:": booking.seat_id,
        "message": "Бронь успешно оплачена"
    }

