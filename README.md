# Roadmap → PPTX

> **Версия:** 1.24.6

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

## Docker на Linux / Unix-сервере

Поставка для обычного Linux-сервера (Debian/Ubuntu и другие дистрибутивы)
с Docker Engine и Docker Compose v2, поддерживающим `--wait`.
На BSD и других Unix нужен Linux Docker-host/VM. Python и Node.js на хосте
не требуются. Образ собирается под архитектуру сервера: `amd64` или `arm64`.
Первая сборка требует доступа к Docker Hub, npm и PyPI.

Один контейнер содержит FastAPI и собранный React-интерфейс. Используется один
воркер, непривилегированный пользователь, healthcheck и автозапуск после
перезагрузки при включённой службе Docker. Логи ограничены тремя файлами по 10 МБ.
LibreOffice в образ не входит: PNG-превью загруженных шаблонов недоступны,
валидация шаблонов и экспорт PPTX работают.

### Готовый образ из GitHub Packages

Образ: **`ghcr.io/aalexmora/json-pptx:1.24.6`**.
[Страница пакета](https://github.com/users/aalexmora/packages/container/package/json-pptx).
Один тег содержит Linux `amd64` и `arm64`; Docker выбирает нужную архитектуру.
Каждый образ проверяется на своей архитектуре до отправки в registry.
Образы содержат только приложение, без пользовательских JSON, профилей и шаблонов.

Пакет приватный. Для скачивания нужен GitHub-аккаунт с доступом и **personal
access token (classic)** с `read:packages`. Fine-grained токен для клонирования
Git-репозитория не подходит для GitHub Packages. Введите classic-токен в запросе
Password команды `docker login` (не пароль GitHub):

```bash
docker login ghcr.io -u aalexmora
```

В существующем каталоге установки, например `~/json-pptx-server`:

```bash
git pull --ff-only
docker compose -f docker-compose.ghcr.yml pull
docker compose -f docker-compose.ghcr.yml up -d --no-build --wait --wait-timeout 120
```

При смене способа запуска сохраняйте тот же каталог и Compose project name:
тогда используются прежние тома данных. Для дальнейших `logs`, `stop`, `down`
и резервного копирования также передавайте `-f docker-compose.ghcr.yml`.
Перед обновлением сохраните резервную копию по инструкции ниже.

Для новой установки достаточно скачать `docker-compose.ghcr.yml` из этой ветки
в отдельный каталог и выполнить две команды Compose выше. Git, Python, Node.js
и локальная сборка образа не нужны. Настройки адреса и порта общие для обоих
вариантов. Другой тег или digest задаётся через `JSON_PPTX_IMAGE`.

Публикация выполняется workflow `Publish container`: native-сборка → проверка
UI/API/PPTX и сохранения данных → отправка того же образа → общий manifest.
Версионный тег создаётся только после успешной проверки обеих архитектур.
Доступ к registry в Actions использует встроенный `GITHUB_TOKEN`; личные токены
в репозитории не сохраняются. Включение workflow также предусмотрено шаблоном
`docker/publish-container-workflow.yml`.

Правила авторизации описаны в
[документации GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

### Установка со сборкой из исходников

Репозиторий приватный: на сервере должен быть настроен доступ к GitHub.

```bash
git clone --branch feature/unix-server-container --single-branch https://github.com/aalexmora/json-pptx.git
cd json-pptx
cp .env.example .env
JSON_PPTX_REVISION="$(git rev-parse HEAD)" docker compose up -d --build --wait --wait-timeout 120
curl --fail http://127.0.0.1:8000/api/health
```

Настройки в `.env`:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `JSON_PPTX_BIND` | `127.0.0.1` | Адрес, на котором сервер принимает подключения |
| `JSON_PPTX_PORT` | `8000` | Порт приложения на сервере |
| `JSON_PPTX_CONTAINER_NAME` | `roadmap-pptx` | Имя контейнера; для нескольких установок задайте разные имена и порты |
| `JSON_PPTX_REVISION` | `unknown` | Git revision в метке собранного образа; команда выше передаёт автоматически |

По умолчанию интерфейс доступен на самом сервере по `http://127.0.0.1:8000/`.
Для доступа со своего компьютера можно открыть SSH-туннель
`ssh -L 8000:127.0.0.1:8000 user@server`, затем открыть этот адрес в браузере.
Для доверенной локальной сети задайте `JSON_PPTX_BIND=0.0.0.0` в `.env`,
повторите команду запуска и откройте `http://<адрес-сервера>:8000/`.
В приложении нет авторизации. Для доступа из интернета используйте reverse proxy
с HTTPS и аутентификацией, сохранив привязку приложения к localhost.
Для nginx задайте `client_max_body_size 50m` и проксируйте на `127.0.0.1:8000`.

### Состояние и обновление

```bash
docker compose ps
docker compose logs --tail=100 -f roadmap
# Остановить, сохранив данные:
docker compose down
```

Профиль, логотипы, активный шаблон и остальные настройки хранятся в
`roadmap-data:/app/data`; шаблоны и статичные слайды — в
`roadmap-templates:/app/templates_library`. Оба named volume переживают
пересборку и обычный `docker compose down`. Не используйте `down -v`, если
данные нужны. Сохраняйте имя каталога/Compose-проекта при обновлениях:
смена имени создаёт отдельные тома. При обновлении прежней серверной установки
из того же каталога существующие тома используются повторно.

Холодная резервная копия перед обновлением (из каталога проекта):

```bash
backup="roadmap-state-$(date +%Y%m%d-%H%M%S).tar.gz"
docker compose stop
docker compose run --rm --no-deps -T roadmap tar -czf - data templates_library > "$backup"
docker compose up -d --no-build --wait --wait-timeout 120
tar -tzf "$backup"
```

Убедитесь, что архив создан без ошибок, затем обновляйте из того же каталога:

```bash
git pull --ff-only
JSON_PPTX_REVISION="$(git rev-parse HEAD)" docker compose up -d --build --wait --wait-timeout 120
```

Для отката выберите предыдущий commit командой `git switch --detach <commit>`
и повторите сборку/запуск. Для восстановления данных остановите сервис и
распакуйте проверенный архив в соответствующие тома через одноразовый контейнер
`docker compose run --rm --no-deps -T roadmap tar -xzf - < "$backup"`, затем
запустите сервис. Перед восстановлением сохраните текущую копию данных.

### Проверка контейнера

```bash
bash scripts/smoke-container.sh
```

Проверка создаёт отдельный Compose-проект со случайным свободным портом и
собственными временными томами. Проверяются интерфейс, версия API, план и PPTX
на RU/EN, затем сохранение данных после пересоздания контейнера. В конце
удаляются только ресурсы тестового проекта. Рабочий `.env` не используется.
Workflow `.github/workflows/container.yml` запускает ту же проверку в GitHub
Actions на native Linux amd64 и arm64; его копия сохранена в
`docker/container-workflow.yml`.
Статус конкретного запуска смотрите во вкладке Actions репозитория.

Семантика запуска и ожидания описана в
[документации Docker Compose](https://docs.docker.com/reference/cli/docker/compose/up/).

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

Версия в шапке открывает журнал текущего релиза. Раздел «Отчёты» рассчитывается
по текущему JSON и содержит отдельные вкладки 2026/2027: год определяется только
по `TrDate`, проблемные релизы открываются по `TfsUrl`, проверяются заполненность
и формат `CrDate`, наличие `AppTitle` и Requirements.
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
