"""
Модуль для загрузки и валидации конфигурации маршрутов из YAML файлов
"""
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from pydantic import BaseModel, Field

class RequestSchema(BaseModel):
    type: str
    properties: Dict[str, Any]
    required: List[str] = Field(default_factory=list)

class WebhookDataMapping(BaseModel):
    url: str
    data: Dict[str, Any]

class WebhookConfig(BaseModel):
    enabled: bool = False
    data_mapping: Dict[str, WebhookDataMapping]

class MethodConfig(BaseModel):
    method: str
    request_schema: Optional[RequestSchema] = None
    response: Dict[str, Any]
    webhook: Optional[WebhookConfig] = None

class RouteConfig(BaseModel):
    path: str
    methods: List[MethodConfig]

class Config(BaseModel):
    routes: List[RouteConfig]

def load_configs(config_dir: str = "config") -> Config:
    """
    Загрузка конфигурации из всех YAML файлов в указанной директории
    
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
    
    # Словарь для хранения уникальных путей
    routes_dict: Dict[str, RouteConfig] = {}
    
    # Загрузка всех YAML файлов
    for yaml_file in config_path.glob("*.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
                
            if not config_data or 'routes' not in config_data:
                print(f"Предупреждение: файл {yaml_file} не содержит секции routes")
                continue
                
            # Обработка каждого маршрута
            for route in config_data['routes']:
                route_config = RouteConfig(**route)
                
                # Проверка на конфликты путей
                if route_config.path in routes_dict:
                    existing_route = routes_dict[route_config.path]
                    # Объединение методов
                    existing_methods = {m.method: m for m in existing_route.methods}
                    for method in route_config.methods:
                        if method.method in existing_methods:
                            print(f"Предупреждение: метод {method.method} для пути {route_config.path} "
                                  f"переопределен в файле {yaml_file}")
                        existing_methods[method.method] = method
                    route_config.methods = list(existing_methods.values())
                
                routes_dict[route_config.path] = route_config
                
        except Exception as e:
            print(f"Ошибка при загрузке файла {yaml_file}: {str(e)}")
            continue
    
    if not routes_dict:
        raise ValueError("Не найдено ни одного валидного маршрута в конфигурационных файлах")
    
    return Config(routes=list(routes_dict.values()))

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
        if route.path == path:
            for method_config in route.methods:
                if method_config.method == method:
                    return method_config
            raise ValueError(f"Метод {method} не поддерживается для пути {path}")
    raise ValueError(f"Маршрут {path} не найден") 