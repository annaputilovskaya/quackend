# 🦆 Quackend

> **If it walks like a backend and quacks like a backend...**
> it's just your fake local server — built from an OpenAPI spec in 3 seconds.

Your Swagger/OpenAPI spec → a live mock API. One command, zero config, realistic data. No config. No backend. No waiting.

[![PyPI](https://img.shields.io/pypi/v/quackend.svg)](https://pypi.org/project/quackend/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen.svg)](https://github.com/annaputilovskaya/quackend/actions)
[![Python](https://img.shields.io/pypi/pyversions/quackend.svg)](https://pypi.org/project/quackend/)

## Install

```bash
pip install quackend
```

## Quick start

```bash
quackend start ./swagger.yaml
# Quack! Your mock server is running on 127.0.0.1:8000
```

```bash
quackend start ./swagger.yaml \
  --port 9000 \
  --latency 300 \      # simulate network delay
  --fail-rate 0.05     # 5% responses fail with 500
```

## Why

- OpenAPI v3 + Swagger v2 in → live mock API out.
- Realistic Faker data mapped from your JSON Schema types and formats.
- `example` / `examples` values take priority over generated data.
- Stateful in-memory store: `GET /users/42`, `PUT /users/42`, `DELETE /users/42` keep the same object.
- `--seed` makes the dataset deterministic for your e2e tests.
- Unknown types and `oneOf` don't crash the server — you get a yellow `[WARNING]` instead.

## As a library

```python
from quackend.server import build_app

app = build_app(openapi_dict)
# uvicorn.run(app, host="127.0.0.1", port=8000)
```

## MCP server

`pip install mcp-server-quackend` — let AI agents spin up mocks themselves.

## License

MIT