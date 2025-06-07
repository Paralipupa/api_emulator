"""
Модуль для обработки HTTP запросов
"""

from fastapi import Request, HTTPException, Form
from typing import Dict, Any, Optional
import json
import logging
from datetime import datetime
from .config_loader import RouteConfig
from .webhook_handler import send_webhook
from .template_processor import replace_template_vars
from .logger import log_request_details, log_response
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class RequestHandler:
    """
    Класс для обработки HTTP запросов
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Инициализация обработчика запросов
        
        Args:
            config: конфигурация маршрутов
        """
        self.config = config

    def is_browser_request(self, path: str) -> bool:
        """
        Проверка, является ли запрос стандартным запросом браузера
        
        Args:
            path: путь запроса
            
        Returns:
            bool: True если это стандартный запрос браузера
        """
        browser_paths = {
            '/favicon.ico',
            '/robots.txt',
            '/sitemap.xml',
            '/humans.txt'
        }
        return path in browser_paths

    def validate_data(self, data: Dict[str, Any], schema: Dict[str, Any]) -> None:
        """
        Валидация данных по схеме
        
        Args:
            data: данные для валидации
            schema: схема валидации
            
        Raises:
            HTTPException: если данные не соответствуют схеме
        """
        try:
            # Определяем grant_type
            grant_type = data.get('grant_type')
            if not grant_type:
                raise ValidationError("grant_type is required", model=BaseModel)

            # Определяем обязательные поля в зависимости от grant_type
            required_fields = ['grant_type', 'client_id', 'client_secret']
            if grant_type == 'authorization_code':
                required_fields.append('code')
            elif grant_type == 'password':
                required_fields.extend(['username', 'password'])
            elif grant_type == 'refresh_token':
                required_fields.append('refresh_token')

            # Проверяем наличие всех обязательных полей
            missing_fields = [field for field in required_fields if field not in data]
            if missing_fields:
                raise ValidationError(
                    f"Missing required fields for grant_type={grant_type}: {', '.join(missing_fields)}",
                    model=BaseModel
                )

            # Проверяем значения полей
            for field, value in data.items():
                if field in schema.get('properties', {}):
                    field_schema = schema['properties'][field]
                    if 'enum' in field_schema and value not in field_schema['enum']:
                        raise ValidationError(
                            f"Invalid value for {field}: {value}. Allowed values: {field_schema['enum']}",
                            model=BaseModel
                        )
            
        except ValidationError as e:
            error_msg = (
                "Ошибка валидации данных.\n"
                f"Ошибка: {str(e)}\n\n"
                f"Полученные данные: {json.dumps(data, ensure_ascii=False, indent=2)}\n\n"
                "Ожидаемый формат:\n"
                f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
            )
            logger.error(error_msg)
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Ошибка валидации данных",
                    "message": str(e),
                    "received_data": data,
                    "expected_format": schema
                }
            )

    async def process_request(self, request: Request, path: str) -> Dict[str, Any]:
        """
        Обработка HTTP запроса
        
        Args:
            request: объект запроса
            path: путь запроса
            
        Returns:
            Dict[str, Any]: ответ на запрос
        """
        try:
            # Получение полного пути
            full_path = f"/{path}"

            # Проверка на стандартные запросы браузера
            if self.is_browser_request(full_path):
                logger.debug(f"Пропуск стандартного запроса браузера: {full_path}")
                return {"status_code": 204}

            # Получение метода запроса
            method = request.method
            logger.info(f"Получен запрос: {method} {full_path}")

            # Получение конфигурации для маршрута
            route_config = self.get_route_config(full_path, method)

            # Обработка параметров запроса
            params, body = await self.process_request_data(request, method, route_config)

            # Валидация данных если есть схема
            if route_config.request_schema:
                self.validate_data(params, self._get_schema_dict(route_config.request_schema))

            # Логирование деталей запроса
            log_request_details(request, params, body)

            # Обработка webhook'а если необходимо
            if route_config.webhook and route_config.webhook.enabled:
                await self.process_webhook(route_config, params)

            # Логирование ответа
            log_response(route_config.response)
            
            logger.info(f"Отправлен ответ для {method} {full_path}")
            return route_config.response

        except ValueError as e:
            logger.error(f"Ошибка маршрутизации: {str(e)}")
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def get_route_config(self, path: str, method: str) -> RouteConfig:
        """
        Получение конфигурации маршрута
        
        Args:
            path: путь запроса
            method: метод запроса
            
        Returns:
            RouteConfig: конфигурация маршрута
        """
        from .config_loader import get_route_config
        return get_route_config(path, method, self.config)

    def _get_schema_dict(self, schema: Any) -> Dict[str, Any]:
        """
        Преобразование схемы в словарь
        
        Args:
            schema: схема запроса
            
        Returns:
            Dict[str, Any]: словарь с описанием схемы
        """
        if hasattr(schema, 'dict'):
            return schema.dict()
        elif isinstance(schema, dict):
            return schema
        else:
            return {"type": str(type(schema).__name__)}

    async def process_request_data(
        self, 
        request: Request, 
        method: str, 
        route_config: RouteConfig
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """
        Обработка данных запроса
        
        Args:
            request: объект запроса
            method: метод запроса
            route_config: конфигурация маршрута
            
        Returns:
            tuple[Dict[str, Any], Optional[Dict[str, Any]]]: параметры и тело запроса
        """
        params = {}
        body = None
        
        # Логируем заголовки запроса
        headers = dict(request.headers)
        logger.info(f"Заголовки запроса: {json.dumps(headers, ensure_ascii=False, indent=2)}")
        
        if method in ["POST", "PUT", "PATCH"] and route_config.request_schema:
            try:
                # Получаем тело запроса как текст для логирования
                body_text = await request.body()
                logger.info(f"Тело запроса (raw): {body_text.decode()}")
                
                # Определяем тип контента
                content_type = headers.get("content-type", "").lower()
                logger.info(f"Тип контента: {content_type}")
                
                if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
                    try:
                        # Парсим form данные
                        form_data = await request.form()
                        body = dict(form_data)
                        params = body
                        logger.info(f"Тело запроса (form): {json.dumps(body, ensure_ascii=False, indent=2)}")
                    except Exception as form_error:
                        logger.error(f"Ошибка при парсинге form данных: {str(form_error)}")
                        raise
                else:
                    # Парсим JSON
                    body = await request.json()
                    params = body
                    logger.info(f"Тело запроса (json): {json.dumps(body, ensure_ascii=False, indent=2)}")
                    
            except Exception as e:
                error_msg = (
                    "Ошибка при обработке данных запроса.\n"
                    f"Ошибка: {str(e)}\n\n"
                    f"Полученные данные: {body_text.decode()}\n\n"
                    "Ожидаемый формат:\n"
                    f"{json.dumps(self._get_schema_dict(route_config.request_schema), ensure_ascii=False, indent=2)}"
                )
                logger.error(error_msg)
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Ошибка при обработке данных запроса",
                        "message": str(e),
                        "received_data": body_text.decode(),
                        "expected_format": self._get_schema_dict(route_config.request_schema)
                    }
                )
        else:
            params = dict(request.query_params)
            logger.info(f"Параметры запроса: {json.dumps(params, ensure_ascii=False, indent=2)}")
            
        return params, body

    async def process_webhook(self, route_config: RouteConfig, params: Dict[str, Any]) -> None:
        """
        Обработка webhook'а
        
        Args:
            route_config: конфигурация маршрута
            params: параметры запроса
        """
        webhook_type = params.get("type")
        if not webhook_type:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Не указан тип webhook'а",
                    "expected_params": ["type", "webhook_url"],
                    "example": {
                        "type": "user_created",
                        "webhook_url": "http://example.com/webhook"
                    }
                }
            )

        webhook_config = route_config.webhook.data_mapping.get(webhook_type)
        if not webhook_config:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Неизвестный тип webhook'а: {webhook_type}",
                    "available_types": list(route_config.webhook.data_mapping.keys())
                }
            )

        # Добавляем текущее время в параметры
        params["current_timestamp"] = datetime.utcnow().isoformat()

        # Подготовка данных для webhook'а
        webhook_data = replace_template_vars(webhook_config.data, params)
        webhook_url = replace_template_vars(webhook_config.url, params)

        try:
            # Отправка webhook'а
            webhook_response = await send_webhook(webhook_url, webhook_data)
            logger.info(f"Webhook успешно отправлен: {webhook_response}")
        except Exception as e:
            logger.error(f"Ошибка при отправке webhook'а: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Ошибка при отправке webhook'а",
                    "message": str(e),
                    "webhook_url": webhook_url,
                    "webhook_data": webhook_data
                }
            ) 