# Ревью этапа 1 — скелет + loader + CLI `routes`

- **Fixed point:** `develop` (`017b849`), дифф `git diff develop...HEAD`.
- **Коммиты под ревью:** `93c47f5`, `c7e05b8`, `80f8ad6`, `2fb16ff`, `9082d54`.
- **Метод:** two-axis review (Standards + Spec) через параллельных под-агентов.
- **Дата:** 2026-09-21.

Статусы: **FIX** — исправляем; **RESOLVED** — закрыто правкой конвенций/согласованием; **DECLINE** — принято как есть (с обоснованием).

## Standards (соответствие конвенциям репозитория)

| ID | Стр. | Находка | Статус | Решение |
|----|------|---------|--------|---------|
| S1 | hard | `loader.operation_response_schema`: докстринг обещает «2xx **application/json**», а код читает любой media type. Противоречит §3 и интерфейсу master (`# первая 2xx application/json schema`). | FIX | Добавить фильтр по `application/json`, привести поведение к докстрингу и master. |
| S2 | hard | Нет модульных докстрингов в `tests/**`, заглушено `per-file-ignores`. §4.2 требует согласованной правки конфига. | RESOLVED | Согласовано пользователем; зафиксировано как исключение в §1.4 и §3 CONVENTIONS (commit `54dca59`). |
| S3 | hard | Нейминг тестов не соответствует §5 `test_<unit>_<scenario>_<expected>` (нет `_expected`). | FIX | Переименовать тесты. |
| S4 | judgement | Data Clumps / Primitive Obsession: `iter_operations` отдаёт `tuple[str, str, dict]`, распаковывается в `reporting` и тестах. | DECLINE | Интерфейс `iter_operations` зафиксирован в master (единственный источник правды). |
| S5 | judgement | Speculative Generality: `path_resource`, `operation_response_schema` пока без вызовов в `src/`. | DECLINE | Обе функции обещаны в интерфейсах master и нужны этапу S2. |
| S6 | judgement | Middle Man / неиспользуемый возврат: `render_route_table` печатает и возвращает `Table`; `cli._callback` — пустой no-op. | DECLINE | Возврат `-> rich.table.Table` зафиксирован в master; `_callback` нужен, чтобы Typer 0.27 не сворачивал одно-командное приложение. |
| S7 | judgement | Мёртвый конфиг mypy: `unused section(s): module = ['prance.*', 'tests.*']`. | FIX | Убрать `prance.*` (импортируется только `prance`); `tests.*` неизбежен при `mypy src` и безвреден. |

## Spec (соответствие плану)

| ID | Стр. | Находка | Статус | Решение |
|----|------|---------|--------|---------|
| P1 | partial | Dev-зависимости не как в плане 01 (было `pytest>=8`, `coverage[toml]>=7`; стало `pytest>=7`, `pytest-cov>=4`). | FIX | Выровнять: `pytest>=8`, `coverage[toml]>=7`, убрать неиспользуемый `pytest-cov`. |
| P2 | partial | Метаданные pyproject: `dynamic = ["version"]` + hatch, другое описание, `license = { file = "LICENSE" }`. | DECLINE | `dynamic`/hatch — требование CONVENTIONS §1.5 (single source of truth `__init__.py`); `LICENSE`-файл уже в репо. |
| P3 | partial | Фикстура `petstore.yaml`: `parameters` подняты на уровень path-item вместо каждой операции. | DECLINE | Плановая фикстура не проходит строгий валидатор prance; path-item — валидная форма OpenAPI 3.0 (§4.3 — чиним фикстуру, а не тесты). |
| P4 | scope | `@app.callback()` в `cli.py`, которого нет в плане. | DECLINE | Необходимо для сохранения группы подкоманд в Typer 0.27 (интерфейс `quackend routes <spec>`). |
| P5 | scope | Блоки инструментов в pyproject (ruff/mypy/coverage/import-linter + контракты). | DECLINE | Требование CONVENTIONS §1.4/§7. |
| P6 | scope | Докстринги vs master «никаких комментариев в коде». | DECLINE | Докстринги ≠ комментарии; §3 требует докстринги, master запрещает комментарии-«что». |

## Очерёдность исправлений

1. S1 — фильтр `application/json` в `operation_response_schema` (TDD).
2. S3 — переименование тестов.
3. S7 — упрощение mypy-override `prance`.
4. P1 — выравнивание dev-зависимостей.
5. Финальный DoD.
