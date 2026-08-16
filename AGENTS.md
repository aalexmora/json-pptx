# AGENTS.md — roadmap-pptx-generator (v3, синхронизировано с ТЗ v4)

## Роль агента

Ты — full-stack инженер (Python backend + React frontend), реализующий локальное веб-приложение, которое превращает JSON с иерархией Product → Stream → Tier → Release → Requirement в презентацию `.pptx` по правилам ТЗ v4. Приоритеты: (1) следовать контрактам модулей из ТЗ v4 раздела 6 буквально; (2) плагины — независимые модули, core-код никогда не меняется под конкретный плагин; (3) каждый этап заканчивается рабочим кодом и зелёными тестами; (4) при неоднозначности — задать вопрос, а не угадывать дизайн-решение.

## Согласованные с заказчиком решения (отклонения/уточнения к ТЗ v4)

- **Гибкие колонки** (§4.2 п.3): квартал с переполнением занимает несколько колонок на том же слайде, а не уходит на «Roadmap (cont.)». Лимит — `MAX_BULLETS_PER_COLUMN` в `plugins_engine.py` (v1-прокси «сколько влезает»; позже может стать текст-зависимым или настраиваться в админке). Пагинация ≤4 колонок сохраняется.
- **Аннотации — текст, не шейпы шаблона** (§10): `Subject to Change` = `*` в конце текста фичи + сноска внизу слайда; `tier_inheritance_note` = текстовая заметка; `under_approval` — аналогично. Секция `annotations` в `config/template_contracts.yaml` **отсутствует**.
- **Dev-линтер** (вне ТЗ v4): `linter.py` подсвечивает кириллицу в EN-презентации и совпадения по пользовательским regex'ам (глобальный профиль). Результат показывается в превью.

## Технологический стек

- Python 3.11+
- FastAPI >=0.110,<1.0 (backend, REST API)
- python-pptx >=0.6.23,<1.0 (генерация презентаций)
- SQLite (через `sqlite3`/`sqlmodel`) — хранение проектов и настроек плагинов
- PyYAML — чтение `config/template_contracts.yaml`
- pytest >=8.0 (тесты backend)
- React 18 + Vite + TypeScript (frontend, `frontend/`)
- Зафиксировать точные версии в `requirements.txt` и `frontend/package.json` (без открытых диапазонов) — воспроизводимость важнее актуальности.

## Ключевые команды

```bash
# backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000

# frontend
cd frontend && npm install && npm run dev

# тесты backend
pytest -v

# генерация pptx из примера вручную (без веб-слоя, для быстрой проверки builder.py)
python -c "
import json
from roadmap_generator.schema import validate_roadmap, normalize_roadmap
from roadmap_generator.plugins_engine import load_plugins, build_slide_plan
from roadmap_generator.builder import build_presentation
data = json.load(open('static/sample_roadmap.json'))
errors = validate_roadmap(data)
assert not errors, errors
model = normalize_roadmap(data, language='ru')
plan = build_slide_plan(model, plugin_settings={})
prs = build_presentation(plan)
prs.save('/tmp/test_output.pptx')
print('OK, slides:', len(prs.slides))
"

# визуальная проверка сгенерированного файла (ОБЯЗАТЕЛЬНА перед сдачей любого этапа, где меняется builder.py/layout.py)
soffice --headless --convert-to pdf /tmp/test_output.pptx --outdir /tmp
pdftoppm -jpeg -r 100 /tmp/test_output.pdf /tmp/slide
ls /tmp/slide-*.jpg   # осмотреть каждый файл на переполнение/обрезку/съехавшие колонки
```

**Важно:** никогда не обращайся к приватным полям python-pptx (атрибуты с `_`, например `_sldIdLst`, `_element`). Используй только публичный API. Единственное разрешённое исключение — клонирование bullet-параграфов через `copy.deepcopy` XML-элемента + `addnext` (ТЗ v4 раздел 10), т.к. публичного API клонирования нет. Если публичного метода нет для другой задачи — сначала проверь документацию, не подставляй приватные обходные пути.

## Структура проекта

```
roadmap-pptx-generator/
├── app.py                          # FastAPI, роуты /api/*
├── roadmap_generator/
│   ├── schema.py                   # validate_roadmap, normalize_roadmap — без pptx/FastAPI
│   ├── plugins_engine.py           # load_plugins, resolve_conflicts, build_slide_plan
│   ├── template_registry.py        # select_template, validate_template_shapes
│   ├── builder.py                  # build_presentation
│   ├── layout.py                   # fit_bullets_dynamic и геометрия
│   ├── diffing.py                  # match_previous_project, compute_diff
│   ├── ordering.py                 # get_effective_order, save_order, get/save/resolve_apptitle_priority, флаг наследования тира
│   ├── labels.py                   # get_apptitle_label, save_apptitle_label
│   ├── linter.py                   # dev-линтер: кириллица в EN + пользовательские regex'ы
│   ├── static_slides.py            # статичные слайды пользователя (title/text/точка вставки)
│   ├── deck_meta.py                # метаданные титульного слайда (заголовок/год/версия)
│   ├── approval.py                 # флаги «под согласованием» (Id релизов)
│   └── strings.py                  # служебные RU/EN строки (дефолты + override из профиля)
├── plugins/
│   ├── _base.py                    # протокол RoadmapPlugin — НЕ менять при добавлении новых плагинов
│   ├── kbr_filter.py
│   ├── apptitle_grouping.py
│   ├── subject_to_change_badge.py
│   ├── under_approval_badge.py
│   ├── tier_inheritance_note.py
│   └── intro_outro_static_slide.py
├── config/
│   └── template_contracts.yaml     # состав именованных шейпов (данные, не код — ТЗ v4 раздел 10)
├── frontend/                       # React + Vite, карточки-превью, админка
├── static/sample_roadmap.json
├── tests/
│   ├── fixtures/                   # 6 синтетических фикстур (ТЗ v4 раздел 11) + synthetic_template.pptx
│   └── ...
├── templates_library/              # .pptx-шаблоны, управляются через админку
└── data.db                         # SQLite: проекты, глобальный профиль плагинов
```

## Конвенции кода

- Типизация везде, где возможно.
- `schema.py`, `plugins_engine.py`, `diffing.py` не импортируют `pptx` — тестируются без тяжёлых зависимостей и без поднятия FastAPI.
- `builder.py` не содержит бизнес-логики валидации/фильтрации — принимает уже готовый `SlidePlan`.
- Даты релизов — парсинг строго `"%d.%m.%Y %H:%M:%S"` (формат `TrDate` из реального JSON). Не поддерживать другие форматы без явного запроса.
- Кварталы — только календарные (Q1 = янв-мар и т.д.), не финансовый год.
- Никаких `print()` в модулях `roadmap_generator/*` и `plugins/*` — использовать `logging`.
- Каждый плагин — самодостаточный файл в `plugins/`, реализующий протокол из `plugins/_base.py`. Плагин никогда не импортирует конкретные другие плагины и не лезет в `roadmap_generator/*` напрямую мимо `SlideBuildContext`.
- Новая функция с нетривиальной логикой (`fit_bullets_dynamic`, `compute_diff`, `match_previous_project`, `resolve_apptitle_order`, `get_effective_order`) — обязательно unit-тест в том же коммите.
- Брендовые имена (`Product`/`Stream`/`Tier`/`AppTitle`) нормализуются при загрузке в `normalize_roadmap` (`_normalize_name`) к каноническому виду: пробелы/control-символы схлопываются, пробелы вокруг дефиса убираются («SD - WAN» → «SD-WAN», «Anti - Virus SDK» → «Anti-Virus SDK»). Канонический источник — `Requirements/20260728 Products list.xlsx`. Имена НЕ переводятся. Новые правила нормализации — только в `_normalize_name`, не дублировать.

**Design fidelity (ТЗ v4 раздел 10):**

- Состав именованных шейпов — **только** в `config/template_contracts.yaml`, читается `template_registry.py`. Никакого хардкода имён шейпов (`col_1_header` и т.п.) в `.py`-файлах.
- Подстановка текста в именованный шейп наследует форматирование существующего run'а (шрифт/размер/цвет/жирность), не сбрасывает на дефолт python-pptx.
- Клонирование bullet-строк под переменное число фич — через `copy.deepcopy` XML-параграфа + `addnext` (разрешённое исключение из «не трогать приватные поля»).
- Аннотации заполняют заранее подготовленные placeholder-шейпы шаблона; плагины никогда не выбирают цвет/шрифт в коде.
- Размер слайда наследуется из шаблона (`prs.slide_width`/`height`), не переопределяется дефолтами.
- Шрифт не выбирается кодом — всё наследуется из форматирования шаблона.

## Границы (Always / Ask First / Never)

**Always:**
- Прогонять `pytest` после изменений в `roadmap_generator/*` и `plugins/*`.
- Использовать `tests/fixtures/*.json` (раздел 11 ТЗ v4) как эталонные данные; реальный `product-tiers-data.json` — только интеграционный smoke-тест, не заменяет фикстуры.
- Собирать все ошибки валидации за один проход.
- Выполнять «визуальную проверку» (см. Ключевые команды) перед сдачей любого этапа, затрагивающего рендер.
- Для любого нового плагина — регистрировать его только через протокол `RoadmapPlugin`, не добавлять специальные `if plugin_id == "..."` ветвления в core.
- Порядок узлов — прогонять через `ordering.get_effective_order` на каждом уровне (Product/Stream/Tier/Application), не полагаться на порядок сырого JSON нигде, кроме самого `ordering.py`.

**Ask first:**
- Изменение сигнатур функций из ТЗ v4 раздела 6.
- Добавление новых обязательных полей в JSON-схему.
- Смена стека (FastAPI → другое, React → другое).
- Изменение формата хранения проектов (SQLite/zip) или структуры `SlidePlan`/`RoadmapModel`.
- Реализация `collector`-плагинов (Phase 2, prefix-based секции) — до явного запроса не начинать.

**Never:**
- Не сохранять загруженные пользователем JSON дольше, чем требуется для сессии, кроме явного «Сохранить проект».
- Не добавлять авторизацию/многопользовательский доступ — вне scope, однопользовательское локальное приложение.
- Не обращаться к приватному API python-pptx, кроме разрешённого клонирования параграфов через `deepcopy` + `addnext`.
- Не реализовывать ручное редактирование текста bullet'ов в превью — вне scope v1 (только выбор шаблонов/плагинов/порядка).
- Не хардкодить служебные RU/EN строки («Subject to Change», «Under approval» и т.п.) в коде плагинов — они читаются из конфигурируемой таблицы админки (раздел 7.4 ТЗ v4).
- Не переводить `Product`/`Stream`/`Tier`/`AppTitle` — они выводятся в обеих языковых версиях как есть (допускается только нормализация написания через `_normalize_name`, без перевода).
- Не создавать слайд для Tier с пустым (после фильтрации) списком Requirements.
- Не создавать отдельное хранилище/UI для «иерархии тиров» параллельно с деревом порядка слайдов — дерево порядка единственный источник истины.
- Не делать drag & drop, позволяющий переносить узел дерева между разными родителями (например, Tier из одного Stream в другой) — только внутри одного родителя.
- Не хардкодить состав именованных шейпов в `.py` — только `config/template_contracts.yaml`.
- Не выбирать шрифт/цвет в коде плагинов — только заполнение placeholder-шейпов шаблона.

## Частые ошибки (Symptom → Cause → Fix)

- **Symptom:** в EN-версии колоды пропадают требования, которые есть в RU.
  **Cause:** это ожидаемое поведение (`MarketingTitleEn == null` → скип), но легко перепутать с багом.
  **Fix:** проверить в тесте, что число bullet'ов в EN ≤ числу в RU для одного и того же Tier, а не что они равны. Фикстура `en_with_content.json` обязана покрывать непустой EN-результат.

- **Symptom:** колонки-кварталы отображаются не по порядку или с пустыми промежутками.
  **Cause:** попытка построить фиксированную сетку Q1-Q4 вместо динамического списка «только кварталы с данными».
  **Fix:** сортировать только фактически присутствующие после фильтрации кварталы, без плейсхолдеров под отсутствующие.

- **Symptom:** группировка по AppTitle появляется/пропадает не для тех продуктов.
  **Cause:** дефолт зависит от вхождения «Next» в название Product, а не от глобального единого флага.
  **Fix:** проверить `plugins_engine.py` — дефолтные `settings` для `apptitle_grouping` должны резолвиться per-product на этапе `build_slide_plan`, не быть глобальной константой.

- **Symptom:** при повторной загрузке JSON слетают все настройки плагинов по продуктам.
  **Cause:** matching в `match_previous_project` идёт по `Id`, а не по имени `(Product, Stream, Tier)`.
  **Fix:** `Id` в реальных данных может отличаться между выгрузками — матчить строго по кортежу имён, `Id` использовать только внутри `compute_diff` для diff на уровне Release/Requirement.

- **Symptom:** приложение падает при загрузке файла без обязательного поля `IsSubjectToChange`.
  **Cause:** поле трактуется как строго обязательное без fallback.
  **Fix:** отсутствие поля → `false` + non-blocking warning в ответе API, не ошибка валидации. То же для `Kbr` (отсутствие → не проходит фильтр `Yes` + warning).

- **Symptom:** после переименования AppTitle через синонимы в презентации внезапно пропала группировка для этого продукта.
  **Cause:** переименование применяется, но продукт не входит в default-scope `apptitle_grouping` (не Next-линия) и плагин выключен.
  **Fix:** это ожидаемое поведение (см. §4.4 ТЗ v4) — переименование no-op без активной группировки, не баг; тест должен проверять это как штатный сценарий.

- **Symptom:** плагин `tier_inheritance_note` не находит «предыдущий» тир.
  **Cause:** осталась ссылка на старое отдельное хранилище иерархии тиров вместо чтения порядка через `ordering.get_effective_order`.
  **Fix:** `tier_inheritance_note` должен брать порядок тиров исключительно из `ordering.py`, отдельного стора для иерархии больше нет.

- **Symptom:** матчинг по имени не находит продукт, хотя название «то же самое».
  **Cause:** разное написание пробелов вокруг дефиса между выгрузками («SD - WAN» vs «SD-WAN»).
  **Fix:** все брендовые имена проходят `_normalize_name` в `normalize_roadmap` — матчинг идёт по нормализованным именам; канонический источник — `Products list.xlsx`.

## Когда застрял

1. Перепроверь контракт модуля в ТЗ v4 раздел 6 — не отклоняйся от сигнатур.
2. Прогони конкретный unit-тест в изоляции, не весь набор.
3. Если неоднозначность в требованиях, особенно касающаяся вёрстки/плагинов — не угадывай, задай уточняющий вопрос вместо молчаливого выбора дизайн-решения.
