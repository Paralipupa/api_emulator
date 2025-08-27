"""
Модуль для обработки HTTP запросов
"""

import json
import logging
from fastapi import Request, HTTPException, Form
from typing import Dict, Any, Optional, Callable, Union
from datetime import datetime
from .config_loader import RouteConfig
from .webhook_handler import send_webhook
from .redirect_handler import process_redirect
from .template_processor import replace_template_vars
from .logger import log_request_details, log_response
from src.helpers import get_int
from .utils.generators import (
    generate_random_code,
    generate_access_token,
    generate_refresh_token,
    generate_token_pair,
    generate_verification_code,
)
from pydantic import BaseModel, ValidationError
from src.rate_limit import rate_limit
import time
from functools import wraps
from threading import Lock

logger = logging.getLogger(__name__)

# Глобальный кэш для хранения временных меток запросов
rate_limit_cache = {}
cache_lock = Lock()

def rate_limit(key_prefix: Union[str, Callable[[Request], str]], limit: int, period_sec: int):
    """
    Декоратор для ограничения количества запросов.
    :param key_prefix: строка или функция, принимающая request и возвращающая строку
    :param limit: Максимальное количество запросов
    :param period_sec: Период в секундах
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, request: Request, *args, **kwargs):
            # Получаем динамический или статический префикс
            prefix = key_prefix(request) if callable(key_prefix) else key_prefix
            # Получаем user_id из параметров пути или IP клиента
            user_id = request.path_params.get("user_id") or request.client.host
            key = f"{prefix}:{user_id}"
            now = int(time.time())
            with cache_lock:
                timestamps = rate_limit_cache.get(key, [])
                # Оставляем только те, что в пределах периода
                timestamps = [ts for ts in timestamps if ts > now - period_sec]
                if len(timestamps) >= limit:
                    # Превышен лимит запросов
                    raise HTTPException(status_code=429, detail="Превышен лимит запросов")
                timestamps.append(now)
                rate_limit_cache[key] = timestamps
            return await func(self, request, *args, **kwargs)
        return wrapper
    return decorator


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

    @rate_limit(key_prefix=lambda req: f"request:{req.url.path}", limit=5, period_sec=3600)
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
            result = self.processing_result(
                path, route_config.response, route_config.model_extra, params
            )

            # raise
            return result

        except ValueError as e:
            logger.error(f"Ошибка маршрутизации: {str(e)}")
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            logger.error(f"Неожиданная ошибка: {str(e)}")
            raise HTTPException(status_code=403, detail=str(e))

    def processing_result(self, path, response, extra, params) -> Dict[str, Any]:
        """
        Обработка результата с поддержкой иерархического повторения

        Поддерживает вложенное повторение элементов, например:
        - chats (повторяется N раз)
          - users (для каждого chat повторяется M раз)
        """
        from src.template_processor import StringTemplateReplacer

        # Если нет настроек повторения, возвращаем обычный результат
        if not extra or not extra.get("repeat") or not extra["repeat"].get("items"):
            return replace_template_vars(path, response, params)

        try:
            # Строим иерархию повторений
            hierarchy = self._build_repeat_hierarchy(extra["repeat"]["items"])

            # Выполняем иерархическое повторение
            result = self._execute_hierarchical_repeat(
                path, response, params, hierarchy
            )

            return result

        except Exception as e:
            logger.error(f"Ошибка при обработке иерархического повторения: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def _build_repeat_hierarchy(self, items: list) -> list:
        """
        Строит универсальную иерархию элементов для повторения с поддержкой произвольной глубины

        Args:
            items: список элементов для повторения

        Returns:
            list: иерархически организованный список элементов
        """
        hierarchy = []

        for item in items:
            item_name = item.get("name", "")

            # Разбиваем имя на части по точкам для определения иерархии
            name_parts = item_name.split(".")

            if len(name_parts) == 1:
                # Корневой элемент
                self._add_or_update_root_item(
                    hierarchy, item_name, item.get("count", "1")
                )
            else:
                # Вложенный элемент - строим полную цепочку
                self._build_nested_hierarchy(
                    hierarchy, name_parts, item.get("count", "1")
                )

        return hierarchy

    def _add_or_update_root_item(self, hierarchy: list, name: str, count: str) -> None:
        """
        Добавляет или обновляет корневой элемент в иерархии

        Args:
            hierarchy: текущая иерархия
            name: имя элемента
            count: количество повторений
        """
        # Ищем существующий элемент
        for existing_item in hierarchy:
            if existing_item.get("name") == name:
                existing_item["count"] = count
                return

        # Создаем новый корневой элемент
        root_item = {"name": name, "count": count, "children": []}
        hierarchy.append(root_item)

    def _build_nested_hierarchy(
        self, hierarchy: list, name_parts: list, count: str
    ) -> None:
        """
        Строит вложенную иерархию для многоуровневых элементов

        Args:
            hierarchy: текущая иерархия
            name_parts: части имени (например, ["chats", "users", "messages"])
            count: количество повторений для последнего элемента
        """
        current_level = hierarchy
        parent_name = None

        # Проходим по всем уровням кроме последнего
        for i, part in enumerate(name_parts[:-1]):
            parent_name = part
            child_name = name_parts[i + 1]

            # Ищем родительский элемент на текущем уровне
            parent_item = None
            for existing_item in current_level:
                if existing_item.get("name") == parent_name:
                    parent_item = existing_item
                    break

            if parent_item is None:
                # Создаем родительский элемент если его нет
                parent_item = {
                    "name": parent_name,
                    "count": "1",  # По умолчанию 1
                    "children": [],
                }
                current_level.append(parent_item)

            # Переходим на следующий уровень
            current_level = parent_item["children"]

        # Добавляем последний элемент
        final_child = {"name": name_parts[-1], "count": count}
        current_level.append(final_child)

    def _execute_hierarchical_repeat(
        self, path, response, params, hierarchy
    ) -> Dict[str, Any]:
        """
        Выполняет универсальное иерархическое повторение элементов

        Args:
            path: путь запроса
            response: шаблон ответа
            params: параметры запроса
            hierarchy: иерархия элементов для повторения

        Returns:
            Dict[str, Any]: результат с иерархической структурой
        """
        from src.template_processor import StringTemplateReplacer

        result = {}

        for item in hierarchy:
            item_name = item["name"]
            count = StringTemplateReplacer.replace(path, item["count"], params)
            count = get_int(count)

            if not item.get("children"):
                # Простое повторение без вложенности
                results = []
                for _ in range(count):
                    results.append(replace_template_vars(path, response, params))

                if item_name == "root":
                    result = [item for sublist in results for item in sublist]
                else:
                    # Извлекаем данные по имени элемента
                    extracted_data = self._extract_data_by_name(results, item_name)
                    result[item_name] = extracted_data
            else:
                # Иерархическое повторение с вложенностью
                parent_results = []

                for _ in range(count):
                    # Создаем родительский элемент
                    parent_result = replace_template_vars(path, response, params)

                    # Рекурсивно обрабатываем дочерние элементы
                    nested_data = self._process_nested_children(
                        path, response, params, item["name"], item["children"]
                    )

                    # Объединяем данные
                    parent_result = self._merge_nested_data(
                        parent_result, item_name, nested_data
                    )
                    parent_results.append(parent_result)

                # Объединяем результаты родительских элементов
                if item_name == "root":
                    result = [item for sublist in parent_results for item in sublist]
                else:
                    extracted_parent_data = self._extract_data_by_name(
                        parent_results, item_name
                    )
                    result[item_name] = extracted_parent_data

        return result

    def _process_nested_children(
        self, path, response, params, parent_name, children
    ) -> Dict[str, Any]:
        """
        Рекурсивно обрабатывает дочерние элементы

        Args:
            path: путь запроса
            response: шаблон ответа
            params: параметры запроса
            children: список дочерних элементов

        Returns:
            Dict[str, Any]: данные дочерних элементов
        """
        from src.template_processor import StringTemplateReplacer

        nested_data = {}

        for child_item in children:
            child_name = child_item["name"]
            child_count = StringTemplateReplacer.replace(
                path, child_item["count"], params
            )
            child_count = get_int(child_count)

            if child_item.get("children"):
                # Рекурсивно обрабатываем вложенные дочерние элементы
                child_results = []
                for _ in range(child_count):
                    child_result = replace_template_vars(path, response, params)
                    nested_child_data = self._process_nested_children(
                        path, response, params, child_item["name"], child_item["children"]
                    )
                    child_result = self._merge_nested_data(
                        child_result, child_name, nested_child_data
                    )
                    child_results.append(child_result)

                extracted_child_data = self._extract_data_by_name(
                    child_results, child_name, parent_name
                )
                nested_data[child_name] = extracted_child_data
            else:
                # Простое повторение дочернего элемента
                child_results = []
                for _ in range(child_count):
                    child_results.append(replace_template_vars(path, response, params))

                extracted_child_data = self._extract_data_by_name(
                    child_results, child_name, parent_name
                )
                nested_data[child_name] = extracted_child_data

        return nested_data

    def _extract_data_by_name(self, results: list, name: str, parent_name: str = None) -> list:
        """
        Извлекает данные по имени элемента из списка результатов

        Args:
            results: список результатов
            name: имя элемента для извлечения

        Returns:
            list: извлеченные данные
        """
        extracted_data = []
        for res in results:
            if parent_name:
                if name in res[parent_name][0]:
                    if isinstance(res[parent_name][0][name], list):
                        extracted_data.extend(res[parent_name][0][name])
                    else:
                        extracted_data.append(res[parent_name][0][name])
            else:
                if name in res:
                    if isinstance(res[name], list):
                        extracted_data.extend(res[name])
                    else:
                        extracted_data.append(res[name])
        return extracted_data

    def _merge_nested_data(
        self,
        parent_result: Dict[str, Any],
        parent_name: str,
        nested_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Объединяет данные родительского элемента с вложенными данными

        Args:
            parent_result: результат родительского элемента
            parent_name: имя родительского элемента
            nested_data: вложенные данные

        Returns:
            Dict[str, Any]: объединенный результат
        """
        if parent_name in parent_result:
            if isinstance(parent_result[parent_name], dict):
                # Если родительский элемент - словарь, добавляем вложенные данные
                parent_result[parent_name].update(nested_data)
            else:
                # Если родительский элемент не словарь, создаем новую структуру
                parent_result[parent_name][0][list(nested_data.keys())[0]].extend(list(nested_data.values())[0])
        else:
            # Если родительского элемента нет, создаем его
            parent_result[parent_name] = nested_data

        return parent_result

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
