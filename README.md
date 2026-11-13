# Roadmap → PPTX

> **Версия:** 1.24.3

Локальное веб-приложение: превращает JSON-выгрузку roadmap (иерархия
`Product → Stream → Tier → Release → Requirement`, RU+EN) в готовую `.pptx`-презентацию
в корпоративном дизайне. Один пользователь, запуск локально, без облака.

## Стек

- **Backend:** FastAPI + python-pptx + SQLite (хранение профиля — сейчас JSON-файл `data/profile.json`).
- **Frontend:** React + Vite + TypeScript.
- **Визуальный QA:** LibreOffice (`soffice`) + poppler (`pdftoppm`).

## Запуск

```bash
# 1. Python-окружение
cd Documents/
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Backend + собранный фронтенд (один процесс)
uvicorn app:app --reload --port 8000
```

Открой http://localhost:8000.

Для разработки фронтенда с hot-reload — второй терминал:

```bash
cd frontend && npm install && npm run dev   # проксирует /api на :8000
```

Собрать фронтенд для продакшна: `cd frontend && npm run build` (после этого
`uvicorn` раздаёт `frontend/dist`).

## Docker Desktop на основном Mac

Исходники и история хранятся в локальном Git внутри VM. Основной Mac получает
готовый Linux ARM64 образ: скрипт выполняет `docker load` и запускает Compose
с `--no-build --pull never`. Пересборка и загрузка зависимостей на Mac не нужны.

Для подготовки поставки из чистого коммита в VM нужны Python 3.14, Node.js
и `crane` (Google go-containerregistry). Пути можно передать через `--node`
и `--crane`, если команды отсутствуют в PATH:

```bash
python3 scripts/build-mac-image.py
```

Архив создаётся в `../releases/`. В нём находятся `image.tar.gz`, Mac Compose,
скрипт запуска, SHA-256, версия и полный Git revision. Образ включает собранный
фронтенд и Linux-зависимости Python. Закреплённый официальный Python base из
`docker/base-mac-image.txt` содержит Cairo. Пользовательские данные, `Requirements/`
и зависимости macOS в образ не входят. Отдельный пакет исходников для входа
сборщика создаётся только через `python3 scripts/package-mac.py --source`.

Сборщик проверяет ARM64 ELF-модули и целостность Docker-архива; проверки здесь
не подтверждают запуск Linux-контейнера на основном Mac. Этот этап завершается
пользователем через Docker Desktop после передачи пакета временной ссылкой из VM.

В **Terminal основного Mac, вне окна VM**, распакуйте скачанный пакет и из его
папки выполните:

```bash
bash scripts/run-mac.sh start
```

Скрипт проверяет SHA-256, находит Docker Desktop и использует локальный context
`desktop-linux` с Linux ARM64 движком. После загрузки он сверяет архитектуру,
версию и Git revision образа. Python, Node.js и Git на основном Mac не нужны.
После healthcheck откройте http://127.0.0.1:8000/.

Повторный запуск выполняется той же командой из той же папки; данные остаются
в постоянных томах Compose-проекта `json-pptx-mac`.

```bash
bash scripts/run-mac.sh check    # Docker Desktop готов к работе
bash scripts/run-mac.sh status
bash scripts/run-mac.sh logs
bash scripts/run-mac.sh stop     # остановка с сохранением данных
bash scripts/run-mac.sh backup   # холодная копия данных и прежнего образа
```

Другой порт: `JSON_PPTX_PORT=8001 bash scripts/run-mac.sh start`.

При смене образа скрипт останавливает существующий контейнер и сохраняет оба
тома вместе с прежним образом в `~/Library/Application Support/json-pptx/backups`.
Путь копии печатается в Terminal. При ошибке резервирования прежний контейнер
возобновляется, если он работал. Ошибка нового healthcheck сохраняет копию и
диагностику; успешный запуск при этом не объявляется.

Для восстановления загрузите `image.tar.gz` из нужной копии, создайте два новых
Docker volume и распакуйте `state.tar.gz` в них: каталог `data` соответствует
`/app/data`, `templates` — `/app/templates_library`. Прежний image ID записан в
`image-id.txt`. Запустите этот образ с восстановленными томами на другом порту,
например `127.0.0.1:8001:8000`, и проверьте данные. Исходные тома и текущий
контейнер сохраняйте до проверки восстановления.

## Docker (деплой на сервер)

Один контейнер: FastAPI + собранный фронтенд. Без LibreOffice — PNG-превью
шаблонов в контейнере не генерируются (валидация и сами шаблоны работают).

На машине запуска нужны работающий Docker Engine или Docker Desktop и
Docker Compose v2 с поддержкой `--wait`. Python и Node.js на хосте не нужны:
зависимости устанавливаются при сборке образа.

Из каталога проекта:

```bash
cd /путь/к/json-pptx
docker compose up -d --build --wait --wait-timeout 120
```

Команда собирает образ, запускает сервис в фоне и ожидает успешный healthcheck.
Откройте http://localhost:8000 (при запуске на сервере — `http://<адрес-сервера>:8000`).
Опции ожидания описаны в [документации Docker Compose](https://docs.docker.com/reference/cli/docker/compose/up/).

Проверить состояние и посмотреть логи:

```bash
docker compose ps
curl --fail http://localhost:8000/api/health
docker compose logs --tail=100 -f roadmap
```

Для обновления после получения новых исходников повторите команду запуска.
Остановить сервис с сохранением данных:

```bash
docker compose down
```

- Образ собран multi-stage (Node → Python), без dev-зависимостей.
- Состояние (профиль `data/`, шаблоны `templates_library/`) — в named volumes,
  переживает пересборку.
- Порт `8000`, healthcheck на `/api/health`.
- За reverse-proxy (nginx) достаточно проксировать на `127.0.0.1:8000`;
  для загрузки `.pptx`/JSON поднимите `client_max_body_size` (напр. `50m`).
- Один воркер: состояние хранится in-memory + файлы, реплицировать нельзя.

### Быстрый production-деплой

Скрипт публикует только уже staged-файлы, сам выполняет необходимые проверки,
создаёт commit, отправляет `main` в GitHub, пересобирает сервис на сервере и
проверяет `/api/health`:

```bash
git add -- app.py roadmap_generator/example.py roadmap_generator/version.py tests/test_example.py
./scripts/deploy.sh -m "feat: example change"
```

Backend-тесты и frontend-сборка запускаются только при изменениях соответствующей
части проекта. JSON/XLSX/CSV из `Requirements/`, `frontend/dist`, runtime-данные,
секреты и генерируемая PPTX-фикстура блокируются автоматически. Для изменений
`builder.py`/`layout.py` после визуальной проверки используется
`./scripts/deploy.sh --visual-qa-ok -m "..."`.

Настройки сервера можно переопределить переменными `DEPLOY_HOST`, `DEPLOY_PATH`,
`DEPLOY_SERVICE`, `DEPLOY_CONTAINER`, `DEPLOY_SSH_KEY` и `DEPLOY_HEALTH_URL`.

## Как пользоваться

1. **Загрузите JSON** (вставка, файл или пример).
2. Выберите **язык** (RU/EN) и настройки плагинов (KBR-фильтр, группировка AppTitle).
3. Превью карточек пересчитывается мгновенно; дерево можно массово раскрыть до
   Product/Stream/Tier/фич или настроить поэлементно. Раскрытие выполняется
   кликом по плашке, сортировка — за отдельную drag-ручку. Технические узлы `-`
   скрыты. Каждый Tier показывает полный набор своих фич без наследования и дедупликации.
4. **«Сгенерировать PPTX»** — скачивание готового файла.

При отсутствии `MarketingTitle` (RU) или `MarketingTitleEn` (EN) используется
`Title` требования. В контроле качества появляется неблокирующая ошибка с ID,
языком и отсутствующим полем; требование остаётся в превью и презентации.

Версия в шапке открывает журнал текущего релиза. Раздел «Отчёты» содержит единый
CSV-блок и отдельные вкладки 2026/2027: год определяется только по `TrDate`,
проблемные релизы открываются по `TfsUrl`, а заполненные продукты проверяются по
`CrDate` и полю CSV `ApplicableForProducts`.
When ENG is selected, Reports also scans every MarketingTitleEn for the configured whole-word brand terms (case-insensitive).

Текущий JSON, язык, режим группировки и состояние интерфейса автоматически
сохраняются в браузере и восстанавливаются после обновления страницы. Кнопка
«Очистить сессию» удаляет сохранённый JSON, не затрагивая глобальный профиль.

Админ-возможности (в секциях под превью): титульный слайд, служебные RU/EN строки,
синонимы/приоритет AppTitle, «под согласованием», статичные слайды, библиотека
шаблонов (загрузка `.pptx` + валидация шейпов + PNG-превью).

Таблица именованных шейпов и чек-лист для дизайнера:
[`Requirements/template_placeholder_guide.md`](Requirements/template_placeholder_guide.md).

«Сохранить проект» / «Загрузить проект» — экспорт/импорт JSON-бандла
`{json_data, language, apptitle_mode, profile}`.

## Тесты

```bash
pytest -q          # backend (132 теста)
cd frontend && npm run typecheck && npm run build
```

## Визуальный QA

```bash
soffice --headless --convert-to pdf deck.pptx --outdir /tmp
pdftoppm -jpeg -r 100 /tmp/deck.pdf /tmp/slide
```

## Структура

```
app.py                  # FastAPI, роуты /api/*
roadmap_generator/      # schema, plugins_engine, builder, layout, diffing, ordering,
                        # labels, template_registry, static_slides, deck_meta,
                        # approval, linter, strings, synthetic_template
plugins/                # RoadmapPlugin-плагины (kbr_filter, apptitle_grouping)
config/                 # template_contracts.yaml, template_mapping.yaml
frontend/               # React + Vite + TypeScript
tests/                  # фикстуры + тесты
templates_library/      # загруженные шаблоны (создаётся автоматически)
data/profile.json       # глобальный профиль (автосохранение)
```

## Ключевые решения

- **Гибкие колонки:** квартал с переполнением занимает несколько колонок
  (`MAX_BULLETS_PER_COLUMN = 10`), пагинация ≤4 колонок/слайд.
- **Аннотации — текстовые:** Subject to Change (`*` + единая сноска) и
  «под согласованием» передаются как текст. Для сноски шаблон может содержать
  семантически именованный `TextBox`-плейсхолдер; оформление наследуется из него.
- **Синтетический шаблон разработки** (`tests/fixtures/synthetic_template.pptx`)
  генерируется автоматически; финальный размеченный шаблон загружается через
  админку (§7.1), код рендера при этом не меняется.
- **Имена нормализуются** при загрузке (`SD - WAN` → `SD-WAN`), канонический
  источник — `Requirements/20260728 Products list.xlsx`.
