"""
Модуль для загрузки и валидации конфигурации маршрутов из YAML файлов
"""

import yaml
import logging
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from pydantic import BaseModel, Field, root_validator

logger = logging.getLogger(__name__)


class RequestSchema(BaseModel):
    type: str
    properties: Dict[str, Any]
    required: List[str] = Field(default_factory=list)


class WebhookDataMapping(BaseModel):
    url: str
    data: Dict[str, Any]


class WebhookConfig(BaseModel):
    enabled: bool = False
    data_mapping: Optional[Dict[str, Any]] = None

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


class RedirectParameter(BaseModel):
    name: str
    value: str


class RedirectConfig(BaseModel):
    enabled: bool = False
    url: str
    parameters: Optional[List[RedirectParameter]] = None

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


class MethodConfig(BaseModel):
    method: str = "GET"
    content_type: str = "application/json"
    request_schema: Optional[Dict[str, Any]] = None
    response: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    webhook: Optional[WebhookConfig] = None
    redirect: Optional[RedirectConfig] = None

    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


class RouteConfig(BaseModel):
    path: str
    methods: List[MethodConfig]


class Config(BaseModel):
    routes: List[RouteConfig]


def load_configs(config_dir: str = "config") -> Config:
    """
    Загрузка конфигурации из всех YAML файлов в указанной директории и её подкаталогах

    Args:
        config_dir: путь к директории с конфигурационными файлами

    Returns:
        Config: объединенный объект конфигурации

    Raises:
        FileNotFoundError: если директория не существует
        ValueError: если в файлах есть конфликты путей
    """
    config_path = Path(config_dir)
    if not config_path.exists():
        raise FileNotFoundError(f"Директория с конфигурацией не найдена: {config_dir}")

    
    routes_dict: Dict[str, RouteConfig] = {}

    configs =config_path.rglob("*.yaml")
    for yaml_file in configs:
        try:
            logger.info(f"Загрузка конфигурации из файла: {yaml_file}")
            with open(yaml_file, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if not config_data or "routes" not in config_data:
                logger.warning(f"Файл {yaml_file} не содержит секции routes")
                continue

            for route in config_data["routes"]:
                try:
                    logger.info(f"Обработка маршрута: {route.get('path')}")
                    route_config = RouteConfig(**route)
                    logger.info(f"Маршрут успешно обработан")

                    # Проверка на конфликты путей
                    if route_config.path in routes_dict:
                        existing_route = routes_dict[route_config.path]
                        # Объединение методов
                        existing_methods = {m.method: m for m in existing_route.methods}
                        for method in route_config.methods:
                            if method.method in existing_methods:
                                logger.warning(
                                    f"Метод {method.method} для пути {route_config.path} "
                                    f"переопределен в файле {yaml_file}"
                                )
                            existing_methods[method.method] = method
                        route_config.methods = list(existing_methods.values())

                    routes_dict[route_config.path] = route_config
                except Exception as route_error:
                    logger.error(
                        f"Ошибка при обработке маршрута {route.get('path')}: {str(route_error)}"
                    )
                    continue

        except Exception as e:
            logger.error(f"Ошибка при загрузке файла {yaml_file}: {str(e)}")
            continue

    if not routes_dict:
        raise ValueError(
            "Не найдено ни одного валидного маршрута в конфигурационных файлах"
        )

    return Config(routes=list(routes_dict.values()))


def _match_path_with_params(route_path: str, request_path: str) -> bool:
    """
    Сравнивает путь запроса с путем из конфигурации, учитывая параметры в фигурных скобках
    
    Args:
        route_path: путь из конфигурации (например, /ratings/v1/answer/{reviewId})
        request_path: путь из запроса (например, /ratings/v1/answer/112)
        
    Returns:
        bool: True если пути совпадают с учетом параметров
    """
    # Разбиваем пути на сегменты
    route_segments = route_path.strip('/').split('/')
    request_segments = request_path.strip('/').split('/')
    
    # Если количество сегментов разное, пути не совпадают
    if len(route_segments) != len(request_segments):
        return False
    
    # Сравниваем каждый сегмент
    for route_seg, request_seg in zip(route_segments, request_segments):
        # Если сегмент в конфигурации - параметр (в фигурных скобках)
        if route_seg.startswith('{') and route_seg.endswith('}'):
            continue
        # Если сегменты не совпадают и это не параметр
        if route_seg != request_seg:
            return False
    
    return True


def get_route_config(path: str, method: str, config: Config) -> MethodConfig:
    """
    Получение конфигурации для конкретного маршрута и метода

    Args:
        path: путь запроса
        method: HTTP метод
        config: объект конфигурации

    Returns:
        MethodConfig: конфигурация метода

    Raises:
        ValueError: если маршрут или метод не найдены
    """
    for route in config.routes:
        if _match_path_with_params(route.path, path):
            for method_config in route.methods:
                if method_config.method == method:
                    return method_config
            raise ValueError(f"Метод {method} не поддерживается для пути {path}")
    raise ValueError(f"Маршрут {path} не найден")
