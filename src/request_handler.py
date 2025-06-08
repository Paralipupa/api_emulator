"""
Модуль для обработки HTTP запросов
"""

import json
import logging
from fastapi import Request, HTTPException, Form
from typing import Dict, Any, Optional
from datetime import datetime
from .config_loader import RouteConfig
from .webhook_handler import send_webhook
from .redirect_handler import process_redirect
from .template_processor import replace_template_vars
from .logger import log_request_details, log_response
from .utils.token_generator import (
    generate_random_code,
    generate_access_token,
    generate_refresh_token,
    generate_token_pair,
    generate_verification_code,
)
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class RequestHandler:
    """
    Класс для обработки HTTP запросов
    """

    def __init__(self, config: Dict[str, Any], settings: Any = None):
        """
        Инициализация обработчика запросов

        Args:
            config: конфигурация маршрутов
        """
        self.config = config
        self.settings = settings

    def is_browser_request(self, path: str) -> bool:
        """
        Проверка, является ли запрос стандартным запросом браузера

        Args:
            path: путь запроса

        Returns:
            bool: True если это стандартный запрос браузера
        """
        browser_paths = {"/favicon.ico", "/robots.txt", "/sitemap.xml", "/humans.txt"}
        return path in browser_paths

    def _validate_required_fields(
        self, data: Dict[str, Any], schema: Dict[str, Any]
    ) -> None:
        """
        Проверка обязательных полей в данных

        Args:
            data: данные для валидации
            schema: схема валидации

        Raises:
            ValidationError: если отсутствуют обязательные поля
        """
        required_fields = schema.get("required", [])
        missing_fields = []

        for field in required_fields:
            if "." in field:
                parent_field, child_field = field.split(".", 1)
                if parent_field not in data:
                    missing_fields.append(field)
                elif not isinstance(data[parent_field], dict):
                    missing_fields.append(field)
                elif child_field not in data[parent_field]:
                    missing_fields.append(field)
            else:
                if field not in data:
                    missing_fields.append(field)

        if missing_fields:
            raise ValidationError(
                f"Отсутствуют обязательные поля: {', '.join(missing_fields)}",
                [],
            )

    def _validate_nested_fields(
        self, data: Dict[str, Any], schema: Dict[str, Any]
    ) -> None:
        """
        Проверка вложенных полей в данных

        Args:
            data: данные для валидации
            schema: схема валидации

        Raises:
            ValidationError: если вложенные поля не соответствуют схеме
        """
        properties = schema.get("properties", {})

        for field, value in data.items():
            if field in properties:
                field_schema = properties[field]

                # Проверка вложенных объектов
                if isinstance(value, dict) and "properties" in field_schema:
                    self._validate_nested_fields(value, field_schema)

                    # Проверка обязательных полей во вложенном объекте
                    if "required" in field_schema:
                        for required_field in field_schema["required"]:
                            if required_field not in value:
                                raise ValidationError(
                                    f"Отсутствует обязательное поле {field}.{required_field}",
                                    [],
                                )

    def _validate_field_type(
        self, field: str, value: Any, field_schema: Dict[str, Any]
    ) -> None:
        """
        Проверка типа данных поля

        Args:
            field: имя поля
            value: значение поля
            field_schema: схема поля

        Raises:
            ValidationError: если тип данных не соответствует схеме
        """
        if "type" not in field_schema:
            return

        expected_type = field_schema["type"]
        type_validators = {
            "str": lambda v: isinstance(v, str),
            "string": lambda v: isinstance(v, str),
            "int": lambda v: isinstance(v, int) or v.isdigit(),
            "integer": lambda v: isinstance(v, int) or v.isdigit(),
            "number": lambda v: isinstance(v, (int, float)),
            "boolean": lambda v: isinstance(v, bool),
        }

        if expected_type in type_validators and not type_validators[expected_type](
            value
        ):
            raise ValidationError(
                f"Поле {field} должно быть {self._get_type_name(expected_type)}",
                [],
            )

    def _get_type_name(self, type_name: str) -> str:
        """
        Получение читаемого названия типа данных

        Args:
            type_name: название типа в схеме

        Returns:
            str: читаемое название типа
        """
        type_names = {
            "string": "строкой",
            "integer": "целым числом",
            "number": "числом",
            "boolean": "булевым значением",
        }
        return type_names.get(type_name, type_name)

    def _validate_enum(
        self, field: str, value: Any, field_schema: Dict[str, Any]
    ) -> None:
        """
        Проверка значения поля на соответствие enum

        Args:
            field: имя поля
            value: значение поля
            field_schema: схема поля

        Raises:
            ValidationError: если значение не соответствует enum
        """
        if "enum" in field_schema and value not in field_schema["enum"]:
            raise ValidationError(
                f"Недопустимое значение для поля {field}: {value}. "
                f"Допустимые значения: {field_schema['enum']}",
                [],
            )

    def _validate_conditional_requirements(
        self, data: Dict[str, Any], schema: Dict[str, Any]
    ) -> None:
        """
        Проверка условных требований (allOf)

        Args:
            data: данные для валидации
            schema: схема валидации

        Raises:
            ValidationError: если не выполнены условные требования
        """
        if "allOf" not in schema:
            return

        for condition in schema["allOf"]:
            if "if" not in condition:
                continue

            if_condition = condition["if"]
            then_condition = condition.get("then", {})

            if self._check_condition(data, if_condition):
                self._validate_then_requirements(data, then_condition)

    def _check_condition(
        self, data: Dict[str, Any], if_condition: Dict[str, Any]
    ) -> bool:
        """
        Проверка условия if

        Args:
            data: данные для проверки
            if_condition: условие для проверки

        Returns:
            bool: True если условие выполнено
        """
        if_properties = if_condition.get("properties", {})

        for prop_name, prop_value in if_properties.items():
            if prop_name not in data:
                return False
            if "const" in prop_value and data[prop_name] != prop_value["const"]:
                return False
        return True

    def _validate_then_requirements(
        self, data: Dict[str, Any], then_condition: Dict[str, Any]
    ) -> None:
        """
        Проверка требований then

        Args:
            data: данные для проверки
            then_condition: требования then

        Raises:
            ValidationError: если не выполнены требования then
        """
        then_required = then_condition.get("required", [])
        missing_then_fields = [field for field in then_required if field not in data]
        if missing_then_fields:
            raise ValidationError(
                f"Требуется указать поля: {', '.join(missing_then_fields)}",
                [],
            )

    def _create_validation_error_response(
        self, error: ValidationError, data: Dict[str, Any], schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Создание ответа с ошибкой валидации

        Args:
            error: ошибка валидации
            data: данные, вызвавшие ошибку
            schema: схема валидации

        Returns:
            Dict[str, Any]: ответ с ошибкой
        """
        error_msg = (
            "Ошибка валидации данных.\n"
            f"Ошибка: {str(error)}\n\n"
            f"Полученные данные: {json.dumps(data, ensure_ascii=False, indent=2)}\n\n"
            "Ожидаемый формат:\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        logger.error(error_msg)
        return {
            "error": "Ошибка валидации данных",
            "message": str(error),
            # "received_data": data,
            # "expected_format": schema,
        }

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
            self._validate_required_fields(data, schema)
            self._validate_nested_fields(data, schema)

            for field, value in data.items():
                if field in schema.get("properties", {}):
                    field_schema = schema["properties"][field]
                    self._validate_field_type(field, value, field_schema)
                    self._validate_enum(field, value, field_schema)

            self._validate_conditional_requirements(data, schema)

        except ValidationError as e:
            error_response = self._create_validation_error_response(e, data, schema)
            raise HTTPException(status_code=400, detail=error_response)

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
            full_path = f"/{path}"

            if self.is_browser_request(full_path):
                logger.debug(f"Пропуск стандартного запроса браузера: {full_path}")
                return {"status_code": 204}

            method = request.method
            logger.info(f"Получен запрос: {method} {full_path}")

            route_config = self.get_route_config(full_path, method)

            params, body = await self.process_request_data(
                request, method, route_config
            )

            if route_config.request_schema:
                self.validate_data(
                    params, self._get_schema_dict(route_config.request_schema)
                )

            log_request_details(request, params, body)

            if route_config.webhook and route_config.webhook.enabled:
                await self.process_webhook(route_config, params)

            if route_config.redirect and route_config.redirect.enabled:
                redirect_url = await process_redirect(
                    route_config.redirect.url, route_config.redirect.parameters, params
                )
                return {"status_code": 302, "headers": {"Location": redirect_url}}

            log_response(route_config.response)

            logger.info(f"Отправлен ответ для {method} {full_path}")
            return replace_template_vars(route_config.response, params)

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
        if hasattr(schema, "dict"):
            return schema.dict()
        elif isinstance(schema, dict):
            return schema
        else:
            return {"type": str(type(schema).__name__)}

    async def process_request_data(
        self, request: Request, method: str, route_config: RouteConfig
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

        headers = dict(request.headers)
        logger.info(
            f"Заголовки запроса: {json.dumps(headers, ensure_ascii=False, indent=2)}"
        )

        if method in ["POST", "PUT", "PATCH"] and route_config.request_schema:
            try:
                # Получаем тело запроса как текст для логирования
                body_text = await request.body()
                logger.info(f"Тело запроса (raw): {body_text.decode()}")

                # Определяем тип контента
                content_type = headers.get("content-type", "").lower()
                logger.info(f"Тип контента: {content_type}")

                if (
                    "application/x-www-form-urlencoded" in content_type
                    or "multipart/form-data" in content_type
                ):
                    try:
                        form_data = await request.form()
                        body = dict(form_data)
                        params = body
                        logger.info(
                            f"Тело запроса (form): {json.dumps(body, ensure_ascii=False, indent=2)}"
                        )
                    except Exception as form_error:
                        logger.error(
                            f"Ошибка при парсинге form данных: {str(form_error)}"
                        )
                        raise
                else:
                    body = await request.json()
                    params = body
                    logger.info(
                        f"Тело запроса (json): {json.dumps(body, ensure_ascii=False, indent=2)}"
                    )

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
                        "expected_format": self._get_schema_dict(
                            route_config.request_schema
                        ),
                    },
                )
        else:
            params = dict(request.query_params)
            logger.info(
                f"Параметры запроса: {json.dumps(params, ensure_ascii=False, indent=2)}"
            )

        return params, body

    async def process_webhook(
        self, route_config: RouteConfig, params: Dict[str, Any]
    ) -> None:
        """
        Обработка webhook'а

        Args:
            route_config: конфигурация маршрута
            params: параметры запроса
        """

        webhook_type = params.get("type", "user_created")
        if not (
            webhook_data_mapping := route_config.webhook.data_mapping.get(webhook_type)
        ):
            raise HTTPException(
                status_code=400,
                detail={
                    "error": f"Неизвестный тип webhook'а: {webhook_type}",
                    "available_types": list(route_config.webhook.data_mapping.keys()),
                },
            )

        webhook_data = replace_template_vars(
            webhook_data_mapping.get("data", {}), params
        )
        webhook_url = replace_template_vars(webhook_data_mapping.get("url", ""), params)

        try:
            if webhook_response := await send_webhook(webhook_url, webhook_data):
                logger.info(f"Webhook успешно отправлен: {webhook_response}")
        except Exception as e:
            logger.error(f"Ошибка при отправке webhook'а: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Ошибка при отправке webhook'а",
                    "message": str(e),
                    "webhook_url": webhook_url,
                    "webhook_data": webhook_data,
                },
            )
