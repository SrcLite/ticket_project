from fastapi import FastAPI
from sqlalchemy import text
import logging
from src.api.v1 import booking, seat, auth
from src.core.database import engine
from src.core.logging_config import setup_logging
from src.core.config import settings
from src.core.redis_client import check_redis_connection, redis_client
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

setup_logging()

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not await check_redis_connection():
        raise RuntimeError("Redis недоступен - запуск отменен")
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        logger.info("startup checks passed")
    yield
    await redis_client.close()
    await engine.dispose()

app = FastAPI(
    title='Ticket Booking API',
    description='High-load ticket booking system',
    version='1.0.0',
    lifespan=lifespan,
    debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
    allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'],
)

# Подключаем роутеры
app.include_router(booking.router, prefix="/api/v1", tags=["Booking"])
app.include_router(seat.router, prefix="/api/v1", tags=["Seats"])
app.include_router(auth.router, prefix="/api/v1")

@app.get("/")
async def root():
    return {"message": "Ticket Booking API is running!"}

@app.get("/health")
async def health_check():
    return {"status":"healthy"}
