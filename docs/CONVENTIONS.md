# Конвенции проекта Quackend (архитектура и рабочий процесс)

> Договорённости имеют силу для кода, коммитов, ревью и работы ИИ-агентов.
> При конфликте с явной инструкцией пользователя/агента побеждает инструкция (зафиксировано в §8).
> Язык договорённости — русский (для команды), код и его док-строки — английский.

---

## 1. Архитектурный стиль: Модульная слоистость с инкапсулированным состоянием

Слои — это **модули**, а не просто папки. Модуль = один файл с одной ответственностью, узкой публичной поверхностью и собственным состоянием.

### 1.1 Слои и направление зависимостей

```
Presentation   cli  server  reporting
   │              │      │
Application     store   (единственная инверсия: StoreProtocol)
   │              │
Domain         generator   loader   ← «листья»: чистые, не импортируют модули пакета
```

Правило зависимостей: **импортировать можно только сам модуль и слои «ниже».** Запрещено:
- импорт «вверх» (domain → application/presentation);
- «боковые» импорты между модулями одного слоя (кроме оговоренных);
- проход сквозь слой (cli → generator напрямую, минуя store/server).

| Слой | Модули | Знает про | Запрещено знать |
|---|---|---|---|
| Presentation | `cli`, `server`, `reporting` | app-слой, `loader` | `generator`, приватные поля любого модуля |
| Application | `store` | `generator` | `server`, `cli`, `reporting` |
| Domain | `generator`, `loader` | ничего внутреннего | `store`, `server`, `cli` |

### 1.2 Инкапсуляция состояния

- Каждый модуль владеет своим состоянием и не даёт его мутировать снаружи.
- `store` держит коллекции/сиды в приватных полях; изменение состояния — только через публичные методы (`create/update/delete/ensure`).
- Модули не читают и не пишут приватные атрибуты других модулей. Нарушение = красный CI (ruff `TID` + `import-linter`).

### 1.3 Публичная поверхность

- У модуля есть **узкий публичный API**: функции/классы без ведущего `_`. Всё остальное — `_private` и не импортируется соседями.
- Негласное правило «публичное = контракт»: изменение сигнатуры публичной функции — breaking change (SemVer `minor`/`major`), изменение приватного — свободно.

### 1.4 Проверяемость линтером (договорённость = код в CI)

Добавить в `pyproject.toml`:

```toml
[tool.lint-imports]
contracts = [
    { name = "architecture layers", layers = [
        "quackend.cli",
        "quackend.reporting",
        "quackend.server",
        "quackend.store",
        "quackend.generator",
        "quackend.loader",
    ] },
    { name = "cli is thin", modules = ["quackend.cli"],
      forbidden = ["quackend.generator", "quackend.store"] },
    { name = "server goes through store", modules = ["quackend.server"],
      forbidden = ["quackend.generator"] },
]
```

Контракт `layers` разрешает импорт строго вниз; два `forbidden`-контракта закрывают «проход сквозь слой» (окончательную схему контрактов сверить с документацией import-linter при внедрении).

[tool.ruff]
target-version = "py310"
line-length = 100
src = ["src"]

[tool.ruff.lint]
select = ["F", "E", "W", "I", "UP", "B", "SIM", "TID", "D"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true

[[tool.mypy.overrides]]
module = "tests.*"
strict = false
```

- `convention = "google"` жёстко фиксирует Google style для докстрингов (вместо ручных ignore).
- `ban-relative-imports = "all"`: относительные импорты внутри пакета запрещены — только абсолютные `from quackend.* import ...`.
- `per-file-ignores = { "tests/**" = ["D"] }`: **исключение** — тесты не обязаны иметь докстринги; правило `D` отключено только для `tests/**`. Тесты регулируются §5 (нейминг `test_<unit>_<scenario>_<expected>`, arrange/act/assert), а требование докстрингов §3 относится к публичному API модулей `src/`, а не к тестам.
- mypy: строгий на `src/`, **умеренный** на `tests/` (override, а не exclude — тесты тоже проверяются, но без строгости); флаги `warn_*` ловят typos в конфиге и устаревшие `# type: ignore`.

Обязательные проверки перед PR (см. §7): `lint-imports`, `ruff check`, `ruff format --check`, `mypy src`, покрытие.

### 1.5 Версионирование пакета

- Single source of truth: `src/quackend/__init__.py` (`__version__`), pyproject читает его через hatch:
  ```toml
  [project]
  dynamic = ["version"]
  [tool.hatch.version]
  path = "src/quackend/__init__.py"
  ```
- SemVer: `0.1.x` — фиксы, `0.y.0` — фичи, `1.0.0` — стабилизация публичного API.

---

## 2. Паттерны проектирования (зафиксированные)

| Паттерн | Где живёт | Как применяется |
|---|---|---|
| **Layered architecture** | весь пакет | §1.1, без исключений |
| **Repository** | `store` | `StoreProtocol` (контракт) + in-memory реализация; `server`/MCP/тесты зависят от протокола |
| **Dependency Injection** (ручной) | `server`, `cli` | `build_app(spec, store=...)` — стор передаётся в конструкцию, не создаётся внутри server |
| **Strategy** | `generator` | маппинг `format`/type → producer-функция (словарь колбэков, без if-каскада) |
| **Adapter** | `loader` | оборачивает `prance` в свой API (`load_openapi`); смена парсера = одно место |
| **Factory** | `server` | `build_app` — единственные построение FastAPI-приложения |
| **Decorator** | `server` | ASGI-middleware для `--latency`/`--fail-rate` |
| **Facade** | `cli` | CLI оркестрирует public-API модулей, не залезая в их внутренности |
| **Lazy initialization** | `store` | коллекции ресурсов пре-генерируются при первом обращении (`ensure`) |

**Анти-паттерны (чёрный список):** God object, Service Locator, скрытые циклические импорты, мутация чужого состояния, big-init в конструкторе, смешивание слоёв в одном файле.

---

## 3. Кодовые конвенции

- **Докстринги:** Google style, на английском. Обязательны: модуль (1 строка), публичный класс (1 строка + опциональные секции), публичная функция/метод (параметры, `Returns`, `Raises` при необходимости). Приватные — по желанию. **Исключение:** к тестам (`tests/**`) требование докстрингов не применяется — правило `D` отключено для них в `[tool.ruff.lint.per-file-ignores]` (см. §1.4); тесты регулируются §5. Пример:

  ```python
  def load_openapi(source: str | Path) -> dict:
      """Parse an OpenAPI v3 or Swagger v2 spec and resolve all $refs.

      Args:
          source: local path or URL of the spec file.

      Returns:
          The fully resolved spec as a plain dict.

      Raises:
          PranceError: if the spec is invalid or cannot be loaded.
      """
  ```
- **Комментарии:** только «зачем», не «что». Код самодокументируемый именем + докстрингом. Комментарий-«что» в PR отклонить.
- **Типизация:** аннотации обязательны; `from __future__ import annotations`; `mypy --strict` на `src/`; типы из `typing`/`collections.abc` (`Protocol`, `Callable`, `Iterator`, `Mapping`, `Sequence`) вместо «сырых» `dict`/`list`. Для **входящих параметров** публичных функций используем абстрактные `Mapping`/`Sequence`, а не конкретные `dict`/`list` — это делает API гибким для тестов и реализаций; **возвращаемые** типы остаются конкретными (`-> dict`, `-> list`) ради стабильного контракта.
- **Нейминг:** модули — предпочтительно одно слово в `snake_case` (`loader.py`, не `open_api_loader.py`); если одного слова не хватает — строго два слова в `snake_case` без дефисов (`app_builder.py`), стили не смешивать; функции/переменные `snake_case`; классы `PascalCase`; константы `UPPER_SNAKE`; приватное с `_`.
- **Импорты:** только абсолютные, `from quackend.* import ...`; относительные запрещены (`ban-relative-imports`). Внутри приватных частей модуля — тоже абсолютные.
- **Формат:** ruff, строка ≤100, двойные кавычки, порядок импортов — ruff/isort. Смешиваний `import`/`from` — только по правилам isort.
- **Ошибки:** исключения — с контекстом (`raise ValueError("id must be positive")`); без голых `raise`; вход валидируем в presentation, бизнес-ошибки — в application.

---

## 4. Инженерная целостность (запреты для кода и ИИ-агентов)

Запреты ниже обязательны для людей и ИИ-агентов одинаково. Их нарушение — блокирующий комментарий на ревью и красная метка перед PR.

### 4.1 Запрет костылей без одобрения пользователя

- ИИ (и разработчик) **не имеет права** обходить сложную архитектурную проблему или баг внешней библиотеки (например, `prance`) «грязным» быстрым патчем в обход архитектуры.
- Если системное решение заблокировано (внешний баг, смежный блокер, нехватка контракта), надо **остановить генерацию кода**, выйти в чат к пользователю, объяснить суть проблемы и причину блокировки системного решения и получить **явное одобрение** на костыль до его написания.
- Костыль, написанный без одобрения, подлежит откату или переделке по результатам ревью.

### 4.2 Запрет маскирования проблем

- Категорически запрещено тушить ворнинги или ошибки линтеров и `mypy`.
- Запрещены: пустые блоки `try/except: pass`, необоснованные `# type: ignore`, затыкание типов через `Any` «чтобы тест прошёл», подавление ошибок ради зелёного CI.
- Проблему решаем **системно** — исправлением интерфейсов или логики ядра. Единственная дверь для ограничения строгости — согласованная правка конфигурации (§1.4 `warn_unused_ignores = true` уже отсекает мёртвые ignore-комментарии).

### 4.3 Запрет подгонки тестов под кривое поведение

- Если падает юнит-тест, запрещено менять ожидаемый результат (`assert`) или контракт докстринга под текущее поведение кода.
- Чиним **код**, а не тесты. Изменение ожидания допустимо только тогда, когда доказуемо изменилось требование или контракт — и такое изменение проходит через обычное ревью с объяснением «почему».

---

## 5. Тестирование

- **Стиль:** `test_<unit>_<scenario>_<expected>`; arrange/act/assert, разделённые пустыми строками.
- **Параметризация** вместо копирования тест-кейсов; фикстуры — в `conftest.py` и по возможности функциональные (`yield`).
- **Без `sleep`** в юнит-тестах (latency проверяется e2e/loose-bound, см. план S3).
- **DoD теста:** зелёный + проверка покрытия (порог 80% на `src/quackend`). Красный тест до реализации — норма (TDD).
- Структура `tests/` повторяет `src/` (зеркально).

---

## 6. Git-процесс

- **Сообщения:** Conventional Commits, английский, imperative:
  `feat(store): ...`, `fix(loader): ...`, `refactor: ...`, `test: ...`, `docs: ...`, `ci: ...`, `chore: ...`, `perf: ...`. Subject ≤72 симв., тело — при необходимости «почему».

  ```text
  feat(store): add seed for deterministic datasets

  faker.seed_instance is now applied once per store instance, so a given
  "--seed 42" reproduces identical collections across restarts.
  ```
- **Когда коммитить:** после каждого зелёного теста/шага (2–5 мин работы). Не откладывать на конец дня.
- **Запрещено коммитить:** красные тесты, TODO-заглушки, секреты/токены, лишние артефакты (`dist/`, `.venv/`, кэши), незаконченную работу под чужим сообщением.
- **Ветки:** feature-branch на этап/задачу создаётся **от `develop`** (никогда от `main`): `feat/<slug>` (напр. `feat/quackend-s2-store`), `fix/<slug>`. Мёрдж — через PR **в `develop`**; solo-сценарий: PR создаём себе, ждём зелёного CI, squash-merge с описательным заголовком.
- **`develop` всегда зелёный.** История линейная (squash/`--rebase`), без `WIP`-коммитов в истории.
- **Релизы:** PR `develop → main`, `main` всегда зелёный; тег `v<semver>` на релиз (`v0.1.0`).

---

## 7. Definition of Done (проверки перед PR)

```bash
lint-imports
ruff check .
ruff format --check .
mypy src
python -m coverage run -m pytest && python -m coverage report --fail-under=80
```

`mypy src` = строгая проверка продакшн-кода (тесты попадают через override, когда mypy запущен без `src`-аргумента).

Все пять зелёные + сообщение коммита корректно + без изменений вне задачи → PR.

### 7.1 Единая команда DoD

Пять проверок собраны в один скрипт — разработчик или ИИ-агент перед PR запускает ровно **одну** команду:

```powershell
.\scripts\dod.ps1      # Windows
./scripts/dod.sh       # Linux/macOS/CI
```

Скрипты идентичны по шагам и порядку (1–5), падают с ненулевым кодом при первой же ошибке и печатают, какой шаг не прошёл. `./scripts/dod.sh` — точки входа для будущего make/CI-таргета:

```makefile
dod:
	@bash ./scripts/dod.sh
```

Если PowerShell на машине блокирует выполнение политикой, запускайте:
`powershell -ExecutionPolicy Bypass -File .\scripts\dod.ps1`.

---

## 8. Онбординг агентов (передача договорённости агенту)

В корне репозитория лежит **`AGENTS.md`** (обёртка, которую агент читает первым делом):

```markdown
# AGENTS.md

This file governs how AI agents behave in this repo.

- `docs/CONVENTIONS.md` is binding — read it first.
- TDD: write the failing test before the implementation.
- Commit after every green test/step, as Conventional Commits.
- Never commit broken tests, TODO placeholders, secrets, or unrelated files.
- Create every feature branch from `develop` (never from `main`); open a PR into `develop` only when all checks pass.
- `develop` must always stay green; `main` is release-only.
- Run the DoD script (§7) before opening a PR:
  `.\scripts\dod.ps1` (Windows) / `./scripts/dod.sh` (POSIX/CI).
- Never hack around a problem without user approval; never mask linter/mypy errors; never fit tests to broken code (§4).
- Stay inside the scope of the task. Do not refactor unrelated code.
- User instructions override these conventions when in conflict.
```

Для людей — краткий `CONTRIBUTING.md` (как поставить окружение, единую команду DoD, куда PR).

---

## 9. Границы применений

Договорённость применяется к `quackend` и переносится как шаблон в новые OSS-проекты пользователя: слой-таблица и чеклисты §1–§7 копируются без изменений, различия только в составе модулей.

## Принято

- [ ] Архитектурный стиль (§1) — подтверждено
- [ ] Паттерны (§2) — подтверждено
- [ ] Код и тесты (§3–§5) — подтверждено
- [ ] Git-процесс и DoD (§6–§7) — подтверждено
- [ ] Онбординг агента (§8) — подтверждено