# Ticket Booking API (High-Load)

## Описание
Асинхронное API для бронирования билетов с решением проблемы race conditions.

## Технологии
- FastAPI (асинхронный)
- PostgreSQL + SKIP LOCKED (пессимистичная блокировка)
- Redis (кеширование)
- Celery (фоновые задачи)
- Docker

## Запуск
```bash
docker-compose up -d
alembic upgrade head
