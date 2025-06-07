"""
Модуль для управления логами
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime


class LogManager:
    """
    Класс для управления логами
    """
    
    def __init__(self, log_dir: str = "logs", max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5):
        """
        Инициализация менеджера логов
        
        Args:
            log_dir: директория для логов
            max_bytes: максимальный размер файла лога в байтах
            backup_count: количество файлов для ротации
        """
        self.log_dir = Path(log_dir)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.setup_logging()

    def setup_logging(self) -> None:
        """
        Настройка логирования
        """
        # Создаем директорию для логов, если она не существует
        self.log_dir.mkdir(exist_ok=True)

        # Формат логов
        log_format = "%(asctime)s - %(levelname)s - %(message)s"
        formatter = logging.Formatter(log_format)

        # Хендлер для вывода в консоль
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # Хендлер для записи в файл с ротацией
        file_handler = RotatingFileHandler(
            filename=self.log_dir / "api.log",
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)

        # Настраиваем корневой логгер
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Удаляем существующие хендлеры
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Добавляем новые хендлеры
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    def get_log_files(self) -> list[Path]:
        """
        Получение списка файлов логов
        
        Returns:
            list[Path]: список путей к файлам логов
        """
        log_files = []
        # Основной файл лога
        main_log = self.log_dir / "api.log"
        if main_log.exists():
            log_files.append(main_log)
        
        # Файлы ротации
        for i in range(1, self.backup_count + 1):
            backup_log = self.log_dir / f"api.log.{i}"
            if backup_log.exists():
                log_files.append(backup_log)
        
        return sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True)

    def get_latest_logs(self, lines: int = 100) -> str:
        """
        Получение последних строк из всех логов
        
        Args:
            lines: количество строк для получения из каждого файла
            
        Returns:
            str: последние строки логов
        """
        log_files = self.get_log_files()
        all_logs = []
        
        for log_file in log_files:
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    file_logs = f.readlines()[-lines:]
                    all_logs.extend(file_logs)
            except Exception as e:
                logging.error(f"Ошибка при чтении файла {log_file}: {str(e)}")
        
        return ''.join(all_logs) 