"""
Основной файл приложения
Реализует API сервер, который обрабатывает запросы на основе конфигурации из YAML файлов
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, RedirectResponse
from fastapi.encoders import jsonable_encoder
from src.config_loader import load_configs
from src.request_handler import RequestHandler
from src.log_manager import LogManager
from src.settings import settings
import logging

# Инициализация менеджера логов
log_manager = LogManager(
    log_dir=settings.LOG_DIR,
    max_bytes=settings.LOG_MAX_BYTES,
    backup_count=settings.LOG_BACKUP_COUNT
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    debug=settings.DEBUG
)


def InitializeRequestHandler():
    try:
        config = load_configs()
        logger.info("Конфигурация успешно загружена")
        return RequestHandler(config, settings)
    except Exception as e:
        logger.error(f"Ошибка при загрузке конфигурации: {str(e)}")
        raise

# request_handler = InitializeRequestHandler()

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
        Response: ответ на запрос
    """
    request_handler = InitializeRequestHandler()
    response = await request_handler.process_request(request, path)
    
    if isinstance(response, dict):
        if "status_code" in response:
            if response["status_code"] == 302 and "headers" in response:
                return RedirectResponse(
                    url=response["headers"]["Location"],
                    status_code=302
                )
            return Response(status_code=response["status_code"])
    
    return JSONResponse(content=jsonable_encoder(response))


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
    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
