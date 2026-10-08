from sqlalchemy import Column, Integer, Boolean, DateTime, String
from datetime import datetime

from sqlalchemy.orm import relationship

from src.core.database import Base

class Hall(Base):
    __tablename__ = "halls"
    id = Column(Integer, primary_key=True, index=True, unique=True)
    _name = Column(String(100), nullable=False, default='Зал')
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    seat = relationship('Seat', back_populates='halls',cascade="all, delete-orphan")