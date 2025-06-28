"""
Модуль с вспомогательными функциями для генерации токенов и кодов
"""

import types as t
import secrets
import string
import uuid
import time
import random
from typing import Tuple


class GeneratorId:
    """
    Синглтон-класс для генерации последовательных идентификаторов.
    Использует паттерн Singleton для обеспечения единственного экземпляра на имя.
    """

    _instances = {}

    def __new__(cls, name: str):
        if name not in cls._instances:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[name] = instance
        return cls._instances[name]

    def __init__(self, name: str) -> None:
        if getattr(self, "_initialized", False):
            return
        self.name = name
        self.ids = {}
        self._initialized = True

    def get(self, is_next: bool = True) -> int:
        self.ids.setdefault(self.name, 0)
        if is_next:
            self.ids[self.name] += 1
        return self.ids[self.name]


def generate_random_code(*args, **kwargs) -> str:
    length = kwargs.get("length", 6)
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_random_3(*args, **kwargs) -> int:
    return str(random.randint(1, 3))


def generate_random_6(*args, **kwargs) -> int:
    return str(random.randint(1, 6))


def generate_random_9(*args, **kwargs) -> int:
    return str(random.randint(1, 9))


def generate_access_token(*args, **kwargs) -> str:
    token = f"{uuid.uuid4()}-{int(time.time())}"
    return token


def generate_refresh_token(*args, **kwargs) -> str:
    return str(uuid.uuid4())


def generate_token_pair(*args, **kwargs) -> Tuple[str, str]:
    return generate_access_token(), generate_refresh_token()


def generate_verification_code(*args, **kwargs) -> str:
    return generate_random_code(6)


def generate_session_id(*args, **kwargs) -> str:
    return str(uuid.uuid4())


def generate_hex_string(*args, **kwargs) -> str:
    return secrets.token_hex(16)


def generate_next_id(*args, **kwargs) -> str:
    path = kwargs.get("path", "default")
    return str(GeneratorId(path).get() % 10 + 1)


def generate_string(*args, **kwargs) -> str:
    return "{0} {1}".format(
        kwargs.get("key", "Test"), GeneratorId(kwargs.get("path", "default")).get(False)
    )
