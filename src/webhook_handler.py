"""
Модуль для обработки webhook'ов
"""

import aiohttp
import logging
from typing import Dict, Any, Optional
import json

logger = logging.getLogger(__name__)


async def send_webhook(url: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Отправка webhook'а на указанный URL

    Args:
        url: URL для отправки webhook'а
        data: данные для отправки

    Returns:
        Optional[Dict[str, Any]]: ответ от сервера или None в случае ошибки
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=data) as response:
                # Получаем тип контента
                content_type = response.headers.get("content-type", "").lower()

                # Пробуем получить ответ в зависимости от типа контента
                if "application/json" in content_type:
                    return await response.json()
                else:
                    # Для не-JSON ответов возвращаем текст
                    text = await response.text()
                    return {
                        "status": response.status,
                        "content_type": content_type,
                        "text": text,
                    }

    except aiohttp.ClientError as e:
        logger.error(f"Ошибка при отправке webhook'а на {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при отправке webhook'а: {str(e)}")
        return None
