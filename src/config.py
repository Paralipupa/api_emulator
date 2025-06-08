"""
Модуль конфигурации приложения
Использует pydantic для валидации и загрузки переменных окружения
"""

from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """
    Класс настроек приложения
    Загружает и валидирует переменные окружения
    """
    # Основные настройки приложения
    APP_NAME: str = "Social API Server"
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # Настройки логирования
    LOG_DIR: str = "logs"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT: int = 5
    
    # Настройки безопасности
    SECRET_KEY: str
    ALLOWED_HOSTS: list[str] = ["*"]
    
    WEBHOOK_URL: str = None

    # Настройки базы данных (если потребуется в будущем)
    DATABASE_URL: Optional[str] = None
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Получение настроек приложения с кэшированием
    
    Returns:
        Settings: объект настроек
    """
    return Settings() 