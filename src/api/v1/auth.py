from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.security import (
hash_password,
verify_password,
create_token_pair,
decode_token,
)
from redis.exceptions import RedisError
from src.services.token_service import  TokenService
from src.schemas.auth import (
UserRegister,
UserLogin,
TokenResponse,
RefreshRequest,
UserResponse,
)
from src.models.user import User
from src.api.deps import get_current_user, bearer_scheme
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/auth', tags=['Auth'])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
        data: UserRegister,
        db: AsyncSession=Depends(get_db),
):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "Email уже зарегистрирован")
    user = User(
        name = data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"User registered: {user.email}")
    return user

@router.post("/login", response_model=TokenResponse)
async def login(
        data: UserLogin,
        db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )

    if not user.is_active:
        raise HTTPException(
            status_code = status.HTTP_403_FORBIDDEN,
            detail="Пользователь деактивирован",
        )
    tokens = create_token_pair(user.id, user.token_version)
    logger.info(f"User logged in: {user.email}")
    return tokens

@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
        data: RefreshRequest,
        db: AsyncSession = Depends(get_db),
):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get('type') != 'refresh':
        raise HTTPException(401, "Невалидный refresh-токен")

    jti = payload.get("jti")
    if not jti:
        raise HTTPException(401, "Невалидный refresh-токен")

    user = await db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    if not user.is_active:
        raise HTTPException(403, "Пользователь деактивирован")
    if int(payload.get("ver", 0)) != user.token_version:
        raise HTTPException(401, "Сессия отозвана")

    try:
        # consume_once отзывает токен атомарно: SET NX пропускает только первый запрос,
        # поэтому и повторное использование refresh-токена, и гонка двух запросов отсекаются
        if not await TokenService.consume_once(jti, payload["exp"]):
            raise HTTPException(401, "Refresh-токен отозван или уже использован")
    except RedisError:
        raise HTTPException(503, "Сервис авторизации временно недоступен")

    return create_token_pair(user.id, user.token_version)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
        data: RefreshRequest,
        db: AsyncSession = Depends(get_db),
        credentials = Depends(bearer_scheme)
):
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh" or not payload.get("jti"):
        raise HTTPException(401, "Невалидный refresh-токен")

    user = await db.get(User, int(payload["sub"]))
    if not user:
        return None
    try:
        # отзываем refresh-токен этой сессии
        await TokenService.blacklist(payload["jti"], payload["exp"])
        # и access-токен, которым клиент подтвердил выход
        if credentials:
            access_payload = decode_token(credentials.credentials)
            if access_payload and access_payload.get("jti"):
                await TokenService.blacklist(access_payload["jti"], access_payload["exp"])
    except RedisError:
        # fail-closed: нельзя отвечать "вы вышли", если отозвать токены не удалось
        raise HTTPException(503, "Не удалось завершить сессию")
    return None

@router.post("/logout-all", status_code=204)
async def logout_all(current_user: User = Depends(get_current_user), db=Depends(get_db)):
    await db.execute(
        update(User).where(User.id == current_user.id).values(token_version=User.token_version + 1)
    )
    await db.commit()

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user