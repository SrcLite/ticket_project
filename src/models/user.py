from sqlalchemy import Integer, String, Column, DateTime, Boolean
from datetime import datetime
from sqlalchemy.orm import relationship
from src.core.database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    email = Column(String(100), nullable=False, unique=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default='user', nullable=False)
    token_version = Column(Integer, nullable=False, default=0, server_default='0')
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship('Booking', back_populates='user', cascade='all,delete-orphan')