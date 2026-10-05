# 🦆 Quackend

[English](README.md) | **Русский**

> **Если это выглядит как бекенд и крякает как бекенд...**
> это просто твой фейковый локальный сервер — собранный из OpenAPI-спеки за 3 секунды.

Твоя Swagger/OpenAPI-спека → живое мок-API. Одна команда, ноль конфигурации, реалистичные данные. Без конфига. Без бекенда. Без ожидания.

[![PyPI](https://img.shields.io/pypi/v/quackend.svg)](https://pypi.org/project/quackend/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen.svg)](https://github.com/annaputilovskaya/quackend/actions)
[![Python](https://img.shields.io/pypi/pyversions/quackend.svg)](https://pypi.org/project/quackend/)

## Установка

```bash
pip install quackend
```

## Быстрый старт

```bash
quackend start ./swagger.yaml
```

```text
      Routes
┌────────┬────────┐
│ Method │ Path   │
├────────┼────────┤
│ GET    │ /users │
└────────┴────────┘
quackend v0.1.0
Starting quackend on http://127.0.0.1:8000 (Ctrl+C to stop)
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Таблица маршрутов, строка версии и баннер — это весь вывод `start` при старте;
`--quiet` подавляет все три.

```bash
quackend start ./swagger.yaml \
  --port 9000 \
  --latency 300 \      # имитировать сетевую задержку
  --fail-rate 0.05     # 5% ответов — ошибка 500
```

## Зачем

- OpenAPI v3 + Swagger v2 на входе → живое мок-API на выходе.
- Реалистичные данные Faker, сопоставленные с типами и форматами твоей JSON-схемы.
- `example` / `examples` имеют приоритет над сгенерированными данными.
- Stateful-хранилище в памяти: `GET /users/42`, `PUT /users/42`, `DELETE /users/42` работают с одним и тем же объектом.
- `GET /users/{any-id}` возвращает сгенерированную сущность вместо 404, а одиночные эндпоинты вроде `/me` возвращают один объект — реальный REST работает из коробки.
- `--seed` делает набор данных детерминированным для твоих e2e-тестов.
- Неизвестные типы и `oneOf` не роняют сервер — вместо этого жёлтый `[WARNING]`.

## Как библиотека

```python
from quackend.server import build_app

app = build_app(openapi_dict)
# uvicorn.run(app, host="127.0.0.1", port=8000)
```

## MCP-сервер

`pip install mcp-server-quackend` — позволь AI-агентам поднимать моки самостоятельно.

## Лицензия

MIT
