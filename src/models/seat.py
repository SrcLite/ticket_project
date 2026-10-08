from sqlalchemy import Integer, ForeignKey, Boolean, String, Column, DateTime, Enum as SQLEnum
from datetime import datetime
import enum
from sqlalchemy.orm import relationship
from src.core.database import Base

class SeatStatusEnum(enum.Enum):
    FREE = "free"
    RESERVED = 'reserved'
    SOLD = 'sold'
    UNAVAILABLE = 'unavailable'
    BLOCKED = 'blocked'

class Seat(Base):
    __tablename__ = "seat"
    id = Column(Integer, primary_key=True, index=True)
    hall_id = Column(Integer, ForeignKey("halls.id"))
    status = Column(SQLEnum(SeatStatusEnum, name='SeatStatusEnum', values_callable=lambda x: [e.value for e in x]), default=SeatStatusEnum.FREE, nullable=False)
    # status = Column(SQLEnum(SeatStatusEnum), default=SeatStatusEnum.FREE, nullable=False)
    price = Column(Integer, nullable=False, default=500)
    zone = Column(String(50), default='standard')
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    halls = relationship('Hall', back_populates='seat')
    bookings = relationship("Booking", back_populates='seat', cascade='all, delete-orphan')