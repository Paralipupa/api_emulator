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
    """Преобразует словари с полями value и type, включая datetime"""

    def can_transform(self, data: Dict) -> bool:
        return isinstance(data, dict) and "value" in data and "type" in data

    def transform(self, data: Dict, params: Dict) -> Any:
        # Сначала выполняем подстановку в value
        processed_value = StringTemplateReplacer.replace(data["value"], params)

        try:
            target_type = data["type"].lower()
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

    def _parse_datetime(self, value: Any, format_str: str = None) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        elif isinstance(value, str):
            if format_str:
                timestamp = float(value)
                dt = datetime.fromtimestamp(timestamp)
                return  dt.strftime(format_str)
            return datetime.fromisoformat(value)
        elif isinstance(value, datetime):
            return value
        raise ValueError(f"Cannot convert {value} to datetime")


class StringTemplateReplacer:
    """Заменяет шаблонные переменные в строках"""

    @staticmethod
    def replace(data: Any, params: Dict) -> Any:
        if not isinstance(data, str):
            return data

        for key, value in params.items():
            data = data.replace(f"{{{key}}}", str(value))

        for func_name, func in AVAILABLE_FUNCTIONS.items():
            if f"{{${func_name}}}" in data:
                if func_name == "token_pair":
                    access_token, refresh_token = func()
                    data = data.replace(
                        f"{{${func_name}}}", f"{access_token},{refresh_token}"
                    )
                else:
                    data = data.replace(f"{{${func_name}}}", func())

        return data


class DataProcessor:
    """Обработчик данных с правильным порядком операций"""

    def __init__(self, params: Dict):
        self.params = params
        self.transformers = [TypedValueTransformer()]

    def process(self, data: Union[Dict, List, str]) -> Union[Dict, List, str]:
        # Сначала подстановка во всех данных
        data = self._replace_vars(data)

        # Затем преобразование типов
        return self._transform_data(data)

    def _replace_vars(self, data: Any) -> Any:
        """Рекурсивная подстановка переменных"""
        if isinstance(data, dict):
            return {k: self._replace_vars(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._replace_vars(item) for item in data]
        elif isinstance(data, str):
            return StringTemplateReplacer.replace(data, self.params)
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
    data: Union[dict, list, str], params: dict
) -> Union[dict, list, str]:
    """
    Фасад для обработки данных с правильным порядком операций:
    1. Сначала подстановка переменных
    2. Затем преобразование типов

    Пример использования:
    data = {
        "message": "Hello {name}",
        "count": {
            "value": "{num}",
            "type": "int"
        },
        "date": {
            "value": "2023-01-15",
            "type": "datetime"
        }
    }
    params = {"name": "Alice", "num": "42"}
    """
    processor = DataProcessor(params)
    return processor.process(data)
