"""
Модуль для обработки редиректов
"""

import aiohttp
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlencode
from .config_loader import RedirectParameter
from .utils.token_generator import (
    generate_access_token,
    generate_refresh_token,
    generate_token_pair,
    generate_verification_code,
    generate_session_id,
    generate_hex_string,
    generate_random_code
)
from .utils.common_data import get_webhook_url, get_current_timestamp

logger = logging.getLogger(__name__)

# Словарь доступных функций для подстановки
AVAILABLE_FUNCTIONS = {
    'access_token': generate_access_token,
    'refresh_token': generate_refresh_token,
    'token_pair': generate_token_pair,
    'verification_code': generate_verification_code,
    'session_id': generate_session_id,
    'hash': generate_hex_string,
    'random_code': generate_random_code,
    'webhook_url': get_webhook_url,
    'current_timestamp': get_current_timestamp
}

async def process_redirect(
    url: str, parameters: List[RedirectParameter], params: Dict[str, Any]
) -> str:
    """
    Обработка редиректа с параметрами

    Args:
        url: URL для редиректа
        parameters: список параметров для URL
        params: параметры запроса для подстановки

    Returns:
        str: полный URL для редиректа
    """
    try:
        # Формируем словарь параметров
        query_params = {}
        for param in parameters:
            # Используем атрибуты модели напрямую
            name = param.name
            value = param.value

            # Подставляем значения из params в value
            for key, val in params.items():
                if isinstance(val, (str, int, float, bool)):
                    value = value.replace(f"{{{key}}}", str(val))

            # Проверяем наличие специальных функций в значении
            for func_name, func in AVAILABLE_FUNCTIONS.items():
                if f"{{${func_name}}}" in value:
                    # Вызываем функцию и подставляем результат
                    if func_name == 'token_pair':
                        access_token, refresh_token = func()
                        value = value.replace(f"{{${func_name}}}", f"{access_token},{refresh_token}")
                    else:
                        value = value.replace(f"{{${func_name}}}", func())

            query_params[name] = value

        # Формируем URL с параметрами
        query_string = urlencode(query_params)
        redirect_url = f"{url}?{query_string}"

        logger.info(f"Сформирован URL для редиректа: {redirect_url}")
        return redirect_url

    except Exception as e:
        logger.error(f"Ошибка при формировании URL для редиректа: {str(e)}")
        raise
