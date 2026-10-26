from __future__ import annotations
import asyncio
import itertools
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from src.core.config import settings
from src.core.database import get_db
from src.core.redis_client import redis_client
from src.core.security import create_token_pair, hash_password
from src.main import app
from src.models.booking import Booking, BookingStatusEnum
from src.models.hall import Hall
from src.models.seat import Seat, SeatStatusEnum
from src.models.user import User

PASSWORD = "password123"

PASSWORD_HASH = hash_password(PASSWORD)

TABLES_TO_TRUNCATE = "booking, seat, halls, users"

@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    assert settings.DB_NAME.endswith("_test"), (
        f"Тесты должны идти на тестовой БД (DB_NAME вида *_test), "
        f"а не на {settings.DB_NAME!r}. Запускайте их через сервис tests."
    )
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    try:
        try:
            async with engine.connect() as conn:
                version = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar()
        except Exception as exc:
            raise RuntimeError(
                "Схема тестовой БД не найдена. Примите миграции:"
                "docker compose run --rm tests alembic upgrade head"
            )from exc
        assert version, "В alembic_version пусто - миграции не применены"
        yield engine
    finally:
        await engine.dispose()

@pytest_asyncio.fixture(autouse=True)
async def clean_database(engine:AsyncEngine) -> AsyncIterator[None]:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES_TO_TRUNCATE} RESTART IDENTITY CASCADE"))
    yield

@pytest_asyncio.fixture
async def db_session(engine:AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session

@pytest_asyncio.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(autouse=True)
async def clean_redis() -> AsyncIterator[None]:
    await redis_client.flushdb()
    try:
        yield
    finally:
        await redis_client.flushdb()
        await redis_client.connection_pool.disconnect()

@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[AsyncEngine]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def user_factory(db_session: AsyncSession) -> Callable[..., Awaitable[User]]:
    counter = itertools.count(1)

    async def create(**kwargs) -> User:
        number = next(counter)
        user = User(
            name=kwargs.pop("name", f'user{number}'),
            email=kwargs.pop("email", f"user{number}@example.com"),
            hashed_password=kwargs.pop("hashed_password", PASSWORD_HASH),
            role=kwargs.pop("role", "user"),
            is_active=kwargs.pop("is_active", True),
            token_version=kwargs.pop("token_version", 0),
            **kwargs,
        )
        db_session.add(user)
        await db_session.commit()
        return user
    return create

@pytest.fixture
def hall_factory(db_session: AsyncSession) -> Callable[..., Awaitable[Hall]]:
    async def create(name: str = 'Зал 1', **kwargs) -> Hall:
        hall = Hall(_name=name, is_active=kwargs.pop("is_active", True), **kwargs)
        db_session.add(hall)
        await  db_session.commit()
        return hall
    return create

@pytest.fixture
def seat_factory(
        db_session: AsyncSession, hall_factory: Callable[..., Awaitable[Hall]]
)-> Callable[..., Awaitable[Seat]]:
    async def create(
            hall: Hall | None=None,
            status: SeatStatusEnum = SeatStatusEnum.FREE,
            **kwargs,
    ) -> Seat:
        hall = hall or await hall_factory()
        seat =Seat(
            hall_id=hall.id,
            status = status,
            price = kwargs.pop("price", 500),
            **kwargs,
        )
        db_session.add(seat)
        await db_session.commit()
        return seat
    return create

@pytest.fixture
def booking_factory(
        db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        seat_factory: Callable[..., Awaitable[Seat]],
) -> Callable[..., Awaitable[Booking]]:
    async def create(
            user: User | None = None,
            seat: Seat | None = None,
            status: BookingStatusEnum = BookingStatusEnum.RESERVED,
            **kwargs,
    ) -> Booking:
        user = user or await user_factory()
        seat = seat or await seat_factory()
        if status == BookingStatusEnum.RESERVED and "reserved_until" not in kwargs:
            kwargs["reserved_until"] = datetime.utcnow() + timedelta(minutes=5)
        booking = Booking(user_id = user.id, seat_id = seat.id, status=status, **kwargs)
        db_session.add(booking)
        await db_session.commit()
        return booking
    return create


@pytest.fixture
def tokens_for() -> Callable[[User], dict[str, str]]:
    def create(user: User) -> dict[str,str]:
        return create_token_pair(user.id, user.token_version)

    return create

@pytest.fixture
def auth_headers(
        user_factory: Callable[..., Awaitable[User]],
        tokens_for: Callable[[User], dict[str,str]],
)-> Callable[..., Awaitable[dict[str, str]]]:
    async def create(user: User | None = None) -> dict[str, str]:
        user = user or await user_factory()
        return {"Authorization": f"Bearer {tokens_for(user)['access_token']}"}
    return create

@pytest.fixture
def run_task() -> Callable[..., Awaitable[Any]]:
    async def run(task, *args) -> Any:
        eager = await asyncio.to_thread(task.apply, args=args)
        return eager.get()
    return run