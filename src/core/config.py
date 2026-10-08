from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DEBUG: bool = False
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASS: str = "1234"
    DB_NAME: str = "tickets_db"

    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    BACKEND_CORS_ORIGINS: list[str] = []


    @property
    def DATABASE_URL(self) -> str:
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"


settings = Settings()