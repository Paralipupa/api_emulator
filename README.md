# Configurable API Server

API сервер на Python, который обрабатывает запросы на основе конфигурации из YAML файла.

## Описание

Приложение предоставляет гибкий API, который может обрабатывать любые запросы на основе конфигурации, описанной в YAML файле. Конфигурация определяет:
- Пути (endpoints)
- Поддерживаемые HTTP методы
- Схемы входных данных
- Форматы ответов

## Структура конфигурации

Конфигурация хранится в файле `config/routes.yaml` и имеет следующую структуру:

```yaml
routes:
  - path: /api/endpoint
    methods:
      - method: GET
        response:
          status: success
          data: [...]
      - method: POST
        request_schema:
          type: object
          properties: {...}
        response:
          status: success
          data: {...}
```

## Запуск приложения

### Локальный запуск

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Запустите приложение:
```bash
python app.py
```

### Запуск в Docker

#### Вариант 1: Использование docker-compose (рекомендуется)

1. Запустите приложение:
```bash
docker-compose up -d
```

2. Для просмотра логов:
```bash
docker-compose logs -f
```

3. Для остановки:
```bash
docker-compose down
```

#### Вариант 2: Ручная сборка и запуск

1. Соберите образ:
```bash
docker build -t configurable-api-server .
```

2. Запустите контейнер:
```bash
docker run -p 8000:8000 configurable-api-server
```

## Использование API

После запуска приложения, API будет доступно по адресу http://localhost:8000

### Примеры запросов

1. Получение списка пользователей:
```bash
curl http://localhost:8000/api/users
```

2. Создание нового пользователя:
```bash
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Иван", "email": "ivan@example.com"}'
```

3. Получение списка товаров:
```bash
curl http://localhost:8000/api/products
```

4. Создание нового заказа:
```bash
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1, "products": [1, 2]}'
```

## Добавление новых маршрутов

Для добавления новых маршрутов достаточно отредактировать файл `config/routes.yaml`, добавив новые пути и их конфигурацию. Приложение автоматически начнет обрабатывать новые маршруты после перезапуска.

## Особенности docker-compose

- Монтирование директории `config` позволяет изменять конфигурацию без пересборки образа
- Настроен healthcheck для проверки работоспособности сервиса
- Автоматический перезапуск при сбоях
- Логирование в реальном времени 