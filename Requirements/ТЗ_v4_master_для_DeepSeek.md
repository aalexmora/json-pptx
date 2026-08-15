# ТЗ v4 (мастер-документ): генератор Roadmap-презентаций

## 0. Как пользоваться этим ТЗ с DeepSeek V4 Pro

1. Веди агента по этапам раздела 13, не проси "сделай всё сразу".
2. Раздел 7 фиксирует контракты модулей — не менять без вопроса (см. AGENTS.md, "Ask first").
3. Плагин — независимый модуль в `plugins/`, core-код никогда не патчится под конкретный плагин.
4. Рабочая среда: VS Code + Cline/Roo, DeepSeek V4 Pro через OpenAI-совместимый API (`https://api.deepseek.com/v1`).

## 1. Назначение

Локальное веб-приложение (один пользователь, Windows/Windows VM) превращает JSON-выгрузку roadmap (Product → Stream → Tier → Release → Requirement, RU+EN) в `.pptx`-презентацию в корпоративном дизайне, с контролем пользователя через систему плагинов, без правок кода при добавлении новой логики отображения.

## 2. Модель входных данных

### 2.1 JSON-схема

```jsonc
[
  {
    "Product": "Kaspersky Next",
    "Streams": [
      {
        "Stream": "Kaspersky Next Optimum",     // "-" = нет реального стрима
        "Tiers": [
          {
            "Tier": "Kaspersky Next EDR Foundations",
            "Releases": [
              {
                "Id": 8074887, "Title": "MDR Program 2.5",
                "AppId": 4074325, "AppTitle": "Managed Detection and Response",
                "TrDate": "29.06.2025 21:00:00",   // "%d.%m.%Y %H:%M:%S"
                "Requirements": [
                  {
                    "Id": 5516302, "Title": "[BRQ] ...",
                    "Kbr": "Yes",
                    "MarketingTitleEn": "License management improvements for MSP/MSSP", // может быть null
                    "MarketingTitle": "Улучшения лицензирования для MSP/MSSP",           // обязательно
                    "Visibility": null,             // ИГНОРИРУЕТСЯ полностью
                    "IsSubjectToChange": false       // boolean; если поле отсутствует → false + warning
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
]
```

Правила: `Product/Stream/Tier/AppTitle` не переводятся (одно значение на оба языка). `Stream == "-"` → без Stream-divider слайда. `Tier.Releases == []` (или всё отфильтровано) → слайд для Tier не создаётся. Если у Product нет ни одного непустого Tier — весь Product (включая divider) пропускается. `MarketingTitleEn == null` при EN-презентации → Requirement пропускается целиком в EN, остаётся в RU.

### 2.2 Валидация

`validate_roadmap(data) -> list[str]` — собирает все ошибки за один проход, не бросает на первой. Проверки: `data` — непустой list; каждый Product/Stream/Tier — dict с обязательными строковыми полями; каждый Release — `Id` (уникален глобально), `AppTitle`, `TrDate` (парсится); каждый Requirement — `Id` (уникален глобально), `MarketingTitle` (непустая строка), `Kbr`/`MarketingTitleEn`/`IsSubjectToChange` опциональны (отсутствие — не ошибка, а warning + мягкий fallback: `Kbr` не задан → трактуется как не проходящий default-фильтр `Yes`; `IsSubjectToChange` не задан → `false`).

## 3. Пользовательский сценарий

Загрузка JSON → выбор языка (RU/EN) → парсинг + normalize → применение глобального профиля плагинов и порядка (с попыткой матчинга по именам `(Product, Stream, Tier)` при переоткрытии проекта, см. раздел 8) → карточки-превью с diff-подсветкой → донастройка плагинов/порядка/переименований (мгновенный пересчёт `SlidePlan`, без рендера pptx) → "Сгенерировать pptx" → скачивание. Опционально — "Сохранить проект" (экспорт).

## 4. Логика формирования колоды

### 4.1 Порядок слайдов

```
[Титульный слайд: заголовок, год, версия/дата — вводит пользователь]
для каждого Product (в эффективном порядке, см. 4.3):
    если продукт даёт ≥1 контентный слайд:
        [Product-divider]
        для каждого Stream (эффективный порядок):
            если Stream != "-": [Stream-divider]
            для каждого Tier (эффективный порядок):
                если Releases/Requirements после фильтрации пусты → пропустить
                иначе → [Tier-roadmap слайд(ы), см. 4.2]
[статичные слайды пользователя — по точкам вставки, см. 6.3]
[Финальный слайд "Thank you!"/"Спасибо!"]
```

### 4.2 Tier-roadmap: колонки, группировка, переполнение

1. Собрать Requirements всех Releases тира, применить фильтр `kbr_filter` (по умолчанию: только `Kbr == "Yes"`); для EN — дополнительно отбросить `MarketingTitleEn == null`.
2. Сгруппировать по календарному кварталу `Qx YYYY` из `TrDate`. Пустые после фильтрации кварталы не создаются как колонки.
3. Отсортировать кварталы хронологически; ≤4 — один слайд; >4 — разбить на слайды по 4 колонки, заголовок продолжений — "Roadmap (cont.)" / "Роадмап (продолжение)" (RU/EN редактируется в админке, 6.4).
4. Группировка по `AppTitle` внутри колонки (`apptitle_grouping`) — по умолчанию включена только для продуктов линии Next (по вхождению "Next" в `Product`), для остальных выключена; переключается вручную per-product. Порядок групп — по убыванию количества фич, либо по ручному глобальному приоритету AppTitle (`resolve_apptitle_order`, раздел 7), если задан. Заголовок группы = кастомное имя из `labels.get_apptitle_label`, если задано, иначе исходный `AppTitle`. Заголовок показывается всегда, даже для единственной группы в колонке.
5. Bullet-текст = `MarketingTitle`/`MarketingTitleEn`. Внутри группы — сначала `IsSubjectToChange == false`, затем `true`, помеченные `*`; если на слайде есть хоть один такой bullet — сноска внизу (текст редактируется в админке, 6.4).
6. Плагин `under_approval_badge` (project-scope, ручной, на уровне Release) — бейдж у колонки соответствующего квартала.
7. Плагин `tier_inheritance_note` — если у Tier в дереве порядка (4.3) включён флаг "Показывать наследование", синяя заметка "inc. all features of previous tier(s)" со списком тиров, стоящих выше в дереве в том же Stream.
8. Переполнение bullet-списка внутри колонки — динамический расчёт помещаемости (`fit_bullets_dynamic`) на основе реальных размеров textbox'а шаблона; при нестабильности в эксплуатации — fallback на фиксированный лимит (переключатель в админке), излишек переносится на слайд-продолжение (не обрезается).

### 4.3 Ручной порядок слайдов (дерево, drag & drop)

Единое дерево на экране проектирования: `Product → Stream → Tier → Application (AppTitle-группа внутри Tier)`. Drag & drop только внутри одного родителя (нельзя переносить между разными Stream/Tier). Хранение — глобальный профиль, ключ = путь родителя, значение — упорядоченный список имён детей (`ordering.get_effective_order`/`save_order`). Новые узлы при перезагрузке JSON — в конец родителя, с diff-меткой "новое — проверьте позицию". Флаг "Показывать наследование" (4.2 п.7) висит на узле Tier в этом дереве — это единственный источник истины для порядка тиров, отдельного UI "Иерархия тиров" не существует.

Порядок Application (AppTitle) по умолчанию — авто по убыванию количества фич; ручной приоритет — **единый глобальный список** (`ordering.get_apptitle_priority`), не per-tier (см. допущение №3, раздел 14).

### 4.4 Переименование AppTitle

Глобальная map `{original_AppTitle: custom_label}` (`labels.py`), редактируется инлайн в карточке превью или в админке (раздел 6.5). Применяется по точному регистрозависимому совпадению. No-op, если `apptitle_grouping` выключена для продукта.

## 5. Архитектура плагинов

Простой протокол, без манифест-системы:

```python
# plugins/_base.py — core, не менять при добавлении новых плагинов
from typing import Protocol, Literal
PluginKind = Literal["filter", "grouping", "annotation", "static", "collector"]
PluginScope = Literal["global", "product", "tier"]

class RoadmapPlugin(Protocol):
    id: str
    label: str
    kind: PluginKind
    scope: PluginScope
    def default_settings(self) -> dict: ...
    def apply(self, context: "SlideBuildContext", settings: dict) -> "SlideBuildContext": ...
```

Типы: `filter` (kbr_filter), `grouping` (apptitle_grouping), `annotation` (subject_to_change_badge, under_approval_badge, tier_inheritance_note), `static` (intro_outro_static_slide), `collector` (**Phase 2**, prefix-based секции типа "Targeted solutions:" — интерфейс зарезервирован, не реализуется в v1). Обнаружение — перебор `.py` в `plugins/` при старте, перезапуск для подхвата новых (hot-reload не требуется). Конфликт двух плагинов одного `kind` на одном слайде → UI-алерт со списком конфликтов, слайд помечается "требует внимания", остальная колода собирается. Настройки — глобальный профиль + override per `(Product, Stream, Tier)`.

## 6. Контракты модулей

```python
# roadmap_generator/schema.py — без зависимостей от pptx/FastAPI
def validate_roadmap(data: list) -> list[str]: ...
def normalize_roadmap(data: list, language: Literal["ru","en"]) -> "RoadmapModel": ...

# roadmap_generator/plugins_engine.py
def load_plugins() -> list[RoadmapPlugin]: ...
def resolve_conflicts(active: list[RoadmapPlugin]) -> tuple[list[RoadmapPlugin], list[str]]: ...
def build_slide_plan(model: "RoadmapModel", plugin_settings: dict) -> "SlidePlan": ...
    # используется и для превью в UI, и для финального рендера — один и тот же план

# roadmap_generator/ordering.py
def get_effective_order(parent_path: str, item_names: list[str]) -> list[str]: ...
def save_order(parent_path: str, ordered_names: list[str]) -> None: ...
def get_apptitle_priority() -> list[str]: ...
def save_apptitle_priority(ordered_names: list[str]) -> None: ...
def resolve_apptitle_order(app_titles_with_counts: list[tuple[str, int]]) -> list[str]: ...

# roadmap_generator/labels.py
def get_apptitle_label(original: str) -> str: ...
def save_apptitle_label(original: str, custom_label: str) -> None: ...

# roadmap_generator/template_registry.py
def select_template(slide_type: str, columns_count: int, grouped_by_apptitle: bool) -> str: ...
def validate_template_shapes(template_path: str, required_shape_names: list[str]) -> list[str]: ...
    # required_shape_names ЧИТАЕТСЯ ИЗ config/template_contracts.yaml, не хардкодится в коде (раздел 10)

# roadmap_generator/builder.py
def build_presentation(plan: "SlidePlan") -> "pptx.Presentation": ...

# roadmap_generator/layout.py
def fit_bullets_dynamic(bullets: list[str], textbox_height_in: float,
                         textbox_width_in: float, base_font_pt: int) -> tuple[int, list[str], list[str]]: ...

# roadmap_generator/diffing.py
def match_previous_project(old_model: "RoadmapModel", new_raw: list) -> "MatchResult": ...
def compute_diff(old_model: "RoadmapModel", new_model: "RoadmapModel") -> "DiffResult": ...
```

## 7. Админ-панель

- **7.1 Библиотека шаблонов**: карточки с PNG-превью первого слайда (тем же конвейером `soffice`+`pdftoppm`, что и в визуальном QA), теги `slide_type/columns_count/grouped_by_apptitle`, ошибки `validate_template_shapes` — красной рамкой на карточке со списком отсутствующих слотов. Таблица выбора `slide_type × columns_count × grouped → файл` (выпадающие списки, не код). Версионирование не требуется.
- **7.2 (упразднён)**: "Иерархия тиров" как отдельный UI не существует — заменена деревом порядка (4.3).
- **7.3 Статичные слайды**: библиотека готовых блоков (текст или скопированный `.pptx`-слайд) + точка вставки ("перед/после Product X", "в конце") — сохраняется в проекте.
- **7.4 Редактируемые строки**: RU/EN пары для сноски "Subject to Change", бейджа "Under approval", заголовка продолжения, шаблона фразы наследования тира.
- **7.5 Синонимы AppTitle**: таблица `Оригинал → Кастомное название`.
- **7.6 Приоритет AppTitle**: простой упорядочиваемый список (глобальный, см. 4.3).
- Однопользовательская, без разграничения прав.

## 8. Diff и повторное открытие проекта

Проектный файл = снимок JSON + язык + глобальный профиль плагинов/порядка/синонимов + per-product override + статичные слайды + ручные "under approval" + метаданные титула. При новой JSON: `match_previous_project` сопоставляет по именам `(Product, Stream, Tier)`, переносит override; несматченное — дефолты. `compute_diff` — по `Id` на уровне Release/Requirement. UI: зелёный бейдж "новое", жёлтый "изменено", приглушённый зачёркнутый "удалено" (секция под Tier, свёрнута по умолчанию), суммарный счётчик на родительском узле дерева.

## 9. Технологический стек

FastAPI + python-pptx + SQLite (backend), React+Vite+TypeScript (frontend), запуск `uvicorn` на localhost, Windows/Windows VM под macOS, только локальное хранилище, без обязательного офлайна, без авторизации, без ручного редактирования bullet-текста в превью (только выбор шаблонов/плагинов/порядка).

## 10. Визуальная точность (design fidelity)

- **Контракт именованных шейпов — данные, не код.** Список обязательных слотов на комбинацию `slide_type × columns_count × grouped_by_apptitle` живёт в `config/template_contracts.yaml`, читается `template_registry.py`. Пример:
  ```yaml
  roadmap:
    columns_2_grouped: [col_1_header, col_1_bullets, col_1_group_header, col_2_header, col_2_bullets, col_2_group_header]
    columns_3_flat: [col_1_header, col_1_bullets, col_2_header, col_2_bullets, col_3_header, col_3_bullets]
  annotations:
    subject_to_change: [annotation_subject_to_change]
    under_approval: [annotation_under_approval]
    tier_inheritance: [annotation_tier_inheritance]
  ```
  Изменение состава слотов (в т.ч. когда появится финальный дизайн-шаблон) — правка только этого файла.
- **Подстановка текста сохраняет форматирование**: замена содержимого именованного шейпа обязана наследовать шрифт/размер/цвет/жирность существующего run'а, не сбрасывать на дефолт python-pptx.
- **Клонирование bullet-строк под переменное число фич** — через глубокое копирование XML-элемента параграфа (`copy.deepcopy` + `addnext`) — единственное официально допустимое исключение из правила AGENTS.md "не трогать приватные поля" python-pptx, т.к. библиотека не даёт публичного API клонирования.
- **Аннотации** (`subject_to_change_badge`, `under_approval_badge`, `tier_inheritance_note`) заполняют текстом заранее подготовленные, отформатированные, скрытые/пустые placeholder-шейпы шаблона — плагины никогда не выбирают цвет/шрифт в коде.
- **Логотипы/декоративная графика** — статичная часть шаблона, генератор их не создаёт и не модифицирует.
- **Размер слайда** наследуется из загруженного шаблона (`prs.slide_width/height`), не переопределяется дефолтами python-pptx.
- **Служебные/документационные слайды внутри multi-slide исходников** (например, слайд-памятка с описанием самих плейсхолдеров) — при нарезке `.pptx`-файла на шаблоны в админке помечаются вручную флагом "не использовать как шаблон".
- **Шрифт** — код не выбирает шрифт; всё, что "зашито" в форматирование шейпов шаблона, наследуется автоматически. Если позже понадобится гарантировать наличие конкретного корпоративного шрифта на машине рендера — это отдельная, не блокирующая v1 задача.

## 11. Тестовые данные и фикстуры

Реальный `product-tiers-data.json` содержит контент только для одного продукта (Kaspersky Next, 2 тира, 5 требований) — остальные продукты корректно дают пустой результат (подтверждает допущение №1), но **не покрывает** сценарии из Definition of Done. Обязательные синтетические фикстуры (`tests/fixtures/`):

- `pagination_5_quarters.json` — Tier с 5+ кварталами → проверка разбиения на "Roadmap (cont.)".
- `subject_to_change_mixed.json` — Requirements с `IsSubjectToChange: true` и `false` в одном квартале → проверка сортировки и сноски.
- `non_next_product_flat.json` — продукт без "Next" в названии, несколько AppTitle → проверка, что группировка по умолчанию выключена (плоский список).
- `en_with_content.json` — Requirements с реально заполненным `MarketingTitleEn` (не null) → проверка, что EN-версия не пустая (текущий пример этого не доказывает, т.к. везде null).
- `missing_optional_fields.json` — часть Requirements без `Kbr`/`IsSubjectToChange` → проверка мягких fallback + warning, не ошибку.
- `tier_hierarchy_next.json` — Stream с 2+ тирами и включённым флагом наследования → проверка `tier_inheritance_note`.

Тесты по реальному `product-tiers-data.json` остаются как "интеграционный smoke-тест на реальных данных", но не заменяют фикстуры выше.

## 12. Соглашение об именах шейпов и шаблон для разработки

`Roadmap_template.pptx` и `roadmap-orig-pptx.pptx` — **референсы дизайна**, не файлы для доработки/переименования шейпов. Финальный размеченный дизайн-шаблон будет предоставлен позже (см. отдельное решение — design fidelity, раздел 10). До его появления:

- Агент создаёт **синтетический шаблон для разработки** (`tests/fixtures/synthetic_template.pptx`, можно сгенерировать программно через `python-pptx` прямо в тестах) с именами шейпов строго по конвенции: `col_{n}_header`, `col_{n}_bullets`, `col_{n}_group_{m}_header` (для группировки AppTitle), `annotation_subject_to_change`, `annotation_under_approval`, `annotation_tier_inheritance` — n от 1 до 4.
- Эта конвенция фиксируется в `config/template_contracts.yaml` (раздел 10) и используется для разработки/тестов Этапов 3–4.
- Когда появится реальный дизайн-шаблон — задача его разметки соответствующими именами шейпов (вручную в PowerPoint или скриптом) выполняется отдельно, без изменения кода `template_registry.py`/`builder.py` — только замена файла в библиотеке шаблонов админки и, при необходимости, правка `template_contracts.yaml`.

## 13. Этапы разработки

0. **Синтетические фикстуры** (раздел 11) — готовятся параллельно с Этапом 1, используются во всех последующих тестах.
1. Схема и валидация (`schema.py`) — тесты на реальном `product-tiers-data.json` + фикстурах.
2. Движок плагинов (`plugins_engine.py`, `plugins/_base.py`, `kbr_filter`, `apptitle_grouping`) + `ordering.py`, `labels.py`. Тесты на конфликтах и дефолтах (Next vs не-Next).
3. Реестр шаблонов (`template_registry.py`) + `config/template_contracts.yaml` + синтетический шаблон (раздел 12).
4. Builder (`builder.py`, `layout.py`) — рендер из `SlidePlan`, пагинация, `fit_bullets_dynamic`, клонирование параграфов. DoD: визуальная проверка через `soffice`→pdf→jpg на всех фикстурах раздела 11.
5. FastAPI + React превью (`app.py`, `frontend/`) — без diff и админки.
6. Плагины-аннотации (`subject_to_change_badge`, `under_approval_badge`, `tier_inheritance_note`) + дерево порядка слайдов (drag & drop, раздел 4.3).
7. Diff/matching (`diffing.py`) + подсветка в UI + экспорт/импорт проекта.
8. Админка (разделы 7.1–7.6).
9. Визуальный QA (сценарии: 1 колонка; 4 колонки с переполнением; группировка + IsSubjectToChange; EN с реальным контентом) + README + финализация AGENTS.md.

## 14. Definition of Done v1

- [ ] Все пункты DoD из предыдущей версии ТЗ (валидация, генерация, тесты, визуальный QA, README).
- [ ] Все фикстуры раздела 11 покрыты тестами, включая EN-версию с непустым результатом.
- [ ] Дерево порядка (4.3) сохраняет/восстанавливает позиции при перезагрузке JSON, новые узлы — в конец с diff-меткой.
- [ ] Переименование AppTitle (4.4) переживает перезагрузку JSON.
- [ ] `template_contracts.yaml` — единственное место, где описан состав именованных шейпов; смена состава не требует правок `.py`-файлов.

## 15. Зафиксированные допущения

1. Product без непустых Tier — пропускается целиком (подтверждено на реальных данных).
2. Служебные RU-формулировки бейджей — дефолты в редактируемой таблице (7.4), не финальный текст.
3. Ручной приоритет AppTitle — единый глобальный список, не per-Tier/per-Product.
4. Новый узел дерева порядка — всегда в конец родителя, без эвристик по смыслу названия.
5. Шрифт не выбирается кодом — наследуется из форматирования шаблона; гарантия наличия конкретного корпоративного шрифта на машине рендера — вне scope v1.
6. `Roadmap_template.pptx`/`roadmap-orig-pptx.pptx` используются только как референс вёрстки для разработки логики, не как файлы для прямой доработки шейпов — финальный размеченный шаблон придёт отдельно.
