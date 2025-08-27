import time
from fastapi import Request, HTTPException
from functools import wraps
from threading import Lock

# Глобальный кэш для хранения временных меток запросов
rate_limit_cache = {}
cache_lock = Lock()


def rate_limit(key_prefix: str, limit: int, period_sec: int):
    """
    Декоратор для ограничения количества запросов.
    :param key_prefix: Префикс ключа (например, user_id или IP)
    :param limit: Максимальное количество запросов
    :param period_sec: Период в секундах
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(request: Request, *args, **kwargs):
            user_id = request.path_params.get("user_id") or request.client.host
            key = f"{key_prefix}:{user_id}"
            now = int(time.time())
            with cache_lock:
                timestamps = rate_limit_cache.get(key, [])
                # Оставляем только те, что в пределах периода
                timestamps = [ts for ts in timestamps if ts > now - period_sec]
                if len(timestamps) >= limit:
                    raise HTTPException(status_code=429, detail="Превышен лимит запросов")
                timestamps.append(now)
                rate_limit_cache[key] = timestamps
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator