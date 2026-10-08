from redis.exceptions import RedisError
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.database import get_db
from src.core.security import decode_token
from src.services.token_service import TokenService, logger
from src.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
)-> User:
    auth_exception=HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Невалидный или отсутствующий токен",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise auth_exception

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise auth_exception

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется access-токен",
        )

    jti = payload.get("jti")
    if jti:
        try:
            if await TokenService.is_blacklisted(jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail='Токен отозван',
                )
        except RedisError:
            # best-effort: авторитетная проверка версии идёт ниже по БД,
            # поэтому падение Redis не должно ронять весь API
            logger.exception("Blacklist check failed, skipping")

    user_id = int(payload.get("sub"))
    user = await db.get(User, user_id)
    if not user:
        raise auth_exception
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь деактивирован",
        )
    if int(payload.get("ver", 0)) != user.token_version:
        raise HTTPException(401, "Сессия отозвана")
    return user

async def get_current_admin(
        current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail = 'Недостаточно прав',
        )
    return current_user