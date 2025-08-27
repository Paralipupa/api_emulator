from datetime import datetime
from typing import Union, Any, Dict, List
from abc import ABC, abstractmethod
from .redirect_handler import AVAILABLE_FUNCTIONS


class ValueTransformer(ABC):
    """Абстрактный класс для преобразования значений"""

    @abstractmethod
    def can_transform(self, data: Dict) -> bool:
        pass

    @abstractmethod
    def transform(self, data: Dict, params: Dict) -> Any:
        pass


class TypedValueTransformer(ValueTransformer):
    """Преобразует словари с полями _value и _type, включая datetime"""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__()

    def can_transform(self, data: Dict) -> bool:
        return isinstance(data, dict) and "_value" in data and "_type" in data

    def transform(self, data: Dict, params: Dict) -> Any:
        # Сначала выполняем подстановку в _value
        processed_value = StringTemplateReplacer.replace(
            self.path, data["_value"], params
        )

        try:
            target_type = data["_type"].lower()
            if target_type == "int":
                return int(processed_value)
            elif target_type == "float":
                return float(processed_value)
            elif target_type == "bool":
                if isinstance(processed_value, str):
                    return processed_value.lower() in ("true", "1", "yes")
                return bool(processed_value)
            elif target_type == "str":
                return str(processed_value)
            elif target_type == "datetime":
                return self._parse_datetime(processed_value, data.get("format"))
            return processed_value
        except (ValueError, TypeError):
            return processed_value

    def _parse_datetime(self, _value: Any, format_str: str = None) -> datetime:
        if isinstance(_value, (int, float)):
            return datetime.fromtimestamp(_value)
        elif isinstance(_value, str):
            if format_str:
                timestamp = float(_value)
                dt = datetime.fromtimestamp(timestamp)
                return dt.strftime(format_str)
            return datetime.fromisoformat(_value)
        elif isinstance(_value, datetime):
            return _value
        raise ValueError(f"Cannot convert {_value} to datetime")


class StringTemplateReplacer:
    """Заменяет шаблонные переменные в строках"""

    @staticmethod
    def replace(path:str, data: Any, params: Dict, **kwargs) -> Any:
        if not isinstance(data, str):
            return data

        for key, _value in params.items():
            data = data.replace(f"{{{key}}}", str(_value))

        for func_name, func in AVAILABLE_FUNCTIONS.items():
            if f"{{${func_name}}}" in data:
                if func_name == "token_pair":
                    access_token, refresh_token = func(path=path, key=kwargs.get("key"))    
                    data = data.replace(
                        f"{{${func_name}}}", f"{access_token},{refresh_token}"
                    )
                else:
                    data = data.replace(f"{{${func_name}}}", func(path=path, key=kwargs.get("key")))

        return data


class DataProcessor:
    """Обработчик данных"""

    def __init__(self, path: str, params: Dict):
        self.path = path
        self.params = params
        self.transformers = [TypedValueTransformer(path)]

    def process(self, data: Union[Dict, List, str]) -> Union[Dict, List, str]:
        # Сначала подстановка во всех данных
        data = self._replace_vars(data)

        # Затем преобразование типов
        return self._transform_data(data)

    def _replace_vars(self, data: Any, **kwargs) -> Any:
        """Рекурсивная подстановка переменных"""
        if isinstance(data, dict):
            return {k: self._replace_vars(v, key=k) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_vars(item) for item in data]
        elif isinstance(data, str):
            return StringTemplateReplacer.replace(self.path, data, self.params, key = kwargs.get("key"))
        return data

    def _transform_data(self, data: Any) -> Any:
        """Рекурсивное преобразование типов"""
        if isinstance(data, dict):
            for transformer in self.transformers:
                if transformer.can_transform(data):
                    return transformer.transform(data, self.params)
            return {k: self._transform_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._transform_data(item) for item in data]
        return data


def replace_template_vars(
    path: str, data: Union[dict, list, str], params: dict
) -> Union[dict, list, str]:
    """
    Фасад для обработки данных с правильным порядком операций:
    1. Сначала подстановка переменных
    2. Затем преобразование типов

    Пример использования:
    data = {
        "message": "Hello {name}",
        "count": {
            "_value": "{num}",
            "_type": "int"
        },
        "date": {
            "_value": "2023-01-15",
            "_type": "datetime"
        }
    }
    params = {"name": "Alice", "num": "42"}
    """
    processor = DataProcessor(path, params)
    return processor.process(data)
