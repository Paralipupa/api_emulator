"""
Основной файл приложения
Реализует API сервер, который обрабатывает запросы на основе конфигурации из YAML файлов
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from src.config_loader import load_configs
from src.request_handler import RequestHandler
from src.log_manager import LogManager
import logging
from datetime import datetime
from pathlib import Path


# Инициализация менеджера логов
log_manager = LogManager(
    log_dir="logs",
    max_bytes=10 * 1024 * 1024,  # 10 MB
    backup_count=5  # Хранить 5 файлов ротации
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Social API Server")


try:
    config = load_configs()
    logger.info("Конфигурация успешно загружена")
    request_handler = RequestHandler(config)
except Exception as e:
    logger.error(f"Ошибка при загрузке конфигурации: {str(e)}")
    raise


@app.get("/health")
async def health_check():
    """
    Эндпоинт для проверки здоровья сервера
    
    Returns:
        dict: статус сервера
    """
    return {"status": "ok"}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def handle_request(request: Request, path: str):
    """
    Обработчик всех запросов

    Args:
        request: объект запроса
        path: путь запроса

    Returns:
        JSONResponse: ответ на запрос
    """
    response = await request_handler.process_request(request, path)
    
    if isinstance(response, dict) and "status_code" in response:
        return Response(status_code=response["status_code"])
    
    return JSONResponse(content=response)


@app.get("/logs")
async def get_logs(lines: int = 100):
    """
    Получение последних строк логов
    
    Args:
        lines: количество строк для получения
        
    Returns:
        dict: последние строки логов
    """
    return {"logs": log_manager.get_latest_logs(lines)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
