"""
Модуль для логирования
"""

import logging
import json
from typing import Dict, Any, Optional
from fastapi import Request


logger = logging.getLogger(__name__)


def get_client_info(request: Request) -> Dict[str, str]:
    """
    Получение информации о клиенте
    
    Args:
        request: объект запроса
        
    Returns:
        Dict[str, str]: информация о клиенте
    """
    # Получаем IP-адрес клиента
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0]
    else:
        client_ip = request.client.host if request.client else "unknown"
    
    # Получаем User-Agent
    user_agent = request.headers.get("user-agent", "unknown")
    
    return {
        "ip": client_ip,
        "user_agent": user_agent
    }


def format_log_message(title: str, content: str) -> str:
    """
    Форматирование сообщения лога
    
    Args:
        title: заголовок секции
        content: содержимое секции
        
    Returns:
        str: отформатированное сообщение
    """
    return f"\n=== {title} ===\n{content}"


def log_request_details(request: Request, params: Dict[str, Any], body: Optional[Dict[str, Any]] = None) -> None:
    """
    Логирование деталей запроса
    
    Args:
        request: объект запроса
        params: параметры запроса
        body: тело запроса (для POST, PUT, PATCH)
    """
    # Получаем информацию о клиенте
    client_info = get_client_info(request)
    
    # Формируем информацию о клиенте
    client_info_str = f"IP: {client_info['ip']}\nUser-Agent: {client_info['user_agent']}"
    
    # Логирование заголовков
    headers = dict(request.headers)
    # Удаляем чувствительные данные из заголовков
    sensitive_headers = ['authorization', 'cookie', 'x-api-key']
    for header in sensitive_headers:
        if header in headers:
            headers[header] = '***'
    
    # Формируем все части лога
    log_parts = [
        format_log_message("Информация о клиенте", client_info_str),
        format_log_message("Заголовки запроса", ", ".join(f"{k}: {v}" for k, v in headers.items()))
    ]
    
    # Добавляем параметры, если есть
    if params:
        params_str = ", ".join(f"{k}: {v}" for k, v in params.items())
        log_parts.append(format_log_message("Параметры запроса", params_str))
    
    # Добавляем тело запроса, если есть
    if body:
        body_str = json.dumps(body, ensure_ascii=False, indent=2)
        log_parts.append(format_log_message("Тело запроса", body_str))
    
    # Логируем все одной строкой
    logger.info("".join(log_parts))


def log_response(response: Dict[str, Any]) -> None:
    """
    Логирование ответа
    
    Args:
        response: ответ сервера
    """
    response_str = json.dumps(response, ensure_ascii=False, indent=2)
    logger.info(format_log_message("Ответ сервера", response_str)) 