"""
Модуль с вспомогательными функциями для генерации токенов и кодов
"""

import secrets
import string
import uuid
import time
from typing import Tuple

def generate_random_code(length: int = 6) -> str:
    """
    Генерирует случайный код указанной длины
    
    Args:
        length: длина генерируемого кода
        
    Returns:
        str: случайный код
    """
    return ''.join(secrets.choice(string.digits) for _ in range(length))

def generate_access_token() -> str:
    """
    Генерирует access токен
    
    Returns:
        str: access токен
    """
    # Генерируем UUID и добавляем временную метку для уникальности
    token = f"{uuid.uuid4()}-{int(time.time())}"
    return token

def generate_refresh_token() -> str:
    """
    Генерирует refresh токен
    
    Returns:
        str: refresh токен
    """
    # Используем более длинный токен для refresh
    return str(uuid.uuid4())

def generate_token_pair() -> Tuple[str, str]:
    """
    Генерирует пару access и refresh токенов
    
    Returns:
        Tuple[str, str]: кортеж из access и refresh токенов
    """
    return generate_access_token(), generate_refresh_token()

def generate_verification_code() -> str:
    """
    Генерирует код верификации
    
    Returns:
        str: код верификации
    """
    # Генерируем 6-значный код
    return generate_random_code(6)

def generate_session_id() -> str:
    """
    Генерирует уникальный идентификатор сессии
    
    Returns:
        str: идентификатор сессии
    """
    return str(uuid.uuid4())

def generate_hex_string() -> str:
    """
    Генерирует случайную строку в формате MD5-хеша (32 символа в hex формате)
    
    Returns:
        str: случайная строка в формате hex (32 символа)
    """
    # Генерируем 16 случайных байтов и преобразуем их в hex строку
    return secrets.token_hex(16) 