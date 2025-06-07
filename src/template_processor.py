"""
Модуль для обработки шаблонов
"""

from typing import Dict, Any, Union


def replace_template_vars(data: Union[dict, list, str], params: dict) -> Union[dict, list, str]:
    """
    Замена переменных в шаблоне данными из параметров

    Args:
        data: данные с шаблонными переменными
        params: параметры для замены

    Returns:
        Union[dict, list, str]: данные с замененными переменными
    """
    if isinstance(data, dict):
        return {k: replace_template_vars(v, params) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_template_vars(item, params) for item in data]
    elif isinstance(data, str):
        for key, value in params.items():
            data = data.replace(f"{{{key}}}", str(value))
        return data
    return data 