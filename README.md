# Roadmap → PPTX

> **Версия:** 1.10.1

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

## Docker (деплой на сервер)

Один контейнер: FastAPI + собранный фронтенд. Без LibreOffice — PNG-превью
шаблонов в контейнере не генерируются (валидация и сами шаблоны работают).

```bash
docker compose up -d --build
```

- Образ собран multi-stage (Node → Python), без dev-зависимостей.
- Состояние (профиль `data/`, шаблоны `templates_library/`) — в named volumes,
  переживает пересборку.
- Порт `8000`, healthcheck на `/api/health`.
- За reverse-proxy (nginx) достаточно проксировать на `127.0.0.1:8000`;
  для загрузки `.pptx`/JSON поднимите `client_max_body_size` (напр. `50m`).
- Один воркер: состояние хранится in-memory + файлы, реплицировать нельзя.

## Как пользоваться

1. **Загрузите JSON** (вставка, файл или пример).
2. Выберите **язык** (RU/EN) и настройки плагинов (KBR-фильтр, группировка AppTitle).
3. Превью карточек пересчитывается мгновенно; дерево можно массово раскрыть до
   Product/Stream/Tier/фич или настроить поэлементно. Раскрытие выполняется
   кликом по плашке, сортировка — за отдельную drag-ручку. Технические узлы `-`
   скрыты; у продуктов с реальной иерархией доступно «Наследование».
4. **«Сгенерировать PPTX»** — скачивание готового файла.

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
- **Аннотации — текстовые:** Subject to Change (`*` + единая сноска), наследование
  тира и «под согласованием» передаются как текст. Для наследования и сноски
  шаблон может содержать семантически именованные `TextBox`-плейсхолдеры;
  оформление полностью наследуется из них.
- **Синтетический шаблон разработки** (`tests/fixtures/synthetic_template.pptx`)
  генерируется автоматически; финальный размеченный шаблон загружается через
  админку (§7.1), код рендера при этом не меняется.
- **Имена нормализуются** при загрузке (`SD - WAN` → `SD-WAN`), канонический
  источник — `Requirements/20260728 Products list.xlsx`.
