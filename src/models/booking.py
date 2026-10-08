import enum
from datetime import datetime
from sqlalchemy.orm import relationship
from sqlalchemy import Integer, ForeignKey, String, Column, DateTime, Index, text, Enum as SQLEnum
from src.core.database import Base

class BookingStatusEnum(enum.Enum):
    """Статусы бронирования"""
    PENDING = 'pending'
    RESERVED = 'reserved'
    SOLD = 'sold'
    EXPIRED = 'expired'
    CANCELLED = 'cancelled'
    FAILED = 'failed'

class Booking(Base):
    __tablename__ = "booking"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    seat_id = Column(Integer, ForeignKey("seat.id"))
    created_at = Column(DateTime, default = datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    status = Column(SQLEnum(BookingStatusEnum, name='BookingStatusEnum', values_callable=lambda x: [e.value for e in x]), nullable=False)
    reserved_until = Column(DateTime, nullable=True)
    idempotency_key = Column(String(255), unique=True, nullable=True, index=True)
    __table_args__ = (
        Index(
            "uq_booking_seat_active",
            'seat_id',
            unique=True,
            postgresql_where=text("status IN ('reserved', 'sold')")
        ),
    )
    user = relationship("User", back_populates='bookings')
    seat = relationship('Seat', back_populates='bookings')