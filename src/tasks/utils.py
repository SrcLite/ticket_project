import asyncio
from functools import wraps
from typing import Callable, Any
import logging

logger = logging.getLogger(__name__)

_loop = None

def get_event_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop

def async_task(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args, **kwargs):
        loop = get_event_loop()
        return loop.run_until_complete(func(*args, **kwargs))
    return wrapper
