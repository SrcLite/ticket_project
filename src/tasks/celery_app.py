import asyncio
import logging
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready, task_failure
from src.core.config import settings
from src.core.logging_config import  setup_logging

setup_logging()
logger = logging.getLogger(__name__)

celery_app = Celery(
    'ticket_tasks',
    broker=f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/0',
    backend=f'redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/1',
    include=[
        'src.tasks.cleanup_tasks',
        "src.tasks.notification_tasks",
    "src.tasks.analytics_tasks",
    ]
)

celery_app.conf.update(
    timezone='Europe/Moscow',
    enable_utc=True,

    task_queues={
        'default': {'exchange': 'default', 'routing_key': 'default'},
        'high_priority': {'exchange': 'high_priority', 'routing_key': 'high_priority'},
    },
    task_default_queue='default',
    task_default_routing_key='default',
    beat_schedule={
        'release-expired-seats-every-minute': {
            'task': 'src.tasks.cleanup_tasks.release_expired_seats',
            'schedule': 60.0,
            'options': {'queue': 'high_priority'}
        },
        'log-health-check': {
            'task': 'src.tasks.cleanup_tasks.health_check',
            'schedule': 300.0
        },
        "send-expiry-reminders":{
            "task": "src.tasks.notification_tasks.send_expiry_reminders",
            "schedule": 60.0,
        },
        "aggregate-hourly-stats": {
            "task": "src.tasks.analytics_tasks.aggregate_hourly_stats",
            "schedule": crontab(minute=0),
        },
    },

    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    result_expires=3600,

    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_time_limit=60 * 10,
    task_soft_time_limit=60 * 5,

    worker_concurrency=2,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    logger.info(f'Celery worker готов к работе! PID: {sender.pid}')


@task_failure.connect
def on_task_failure(sender, task_id, exception, traceback, **kwargs):
    logger.error(f"Задача {sender.name} (ID: {task_id}) упала с ошибкой:")
    logger.error(f"Ошибка: {exception}")
    logger.error(f"Трейсбек: {traceback}")

