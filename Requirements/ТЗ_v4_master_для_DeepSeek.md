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
                "TrDate": "29.06.2025 21:00:00",   // "%d.%m.%Y %H:%M:%S" ИЛИ "%m/%d/%Y %I:%M:%S %p" (продакшен)
                "Requirements": [
                  {
                    "Id": 5516302, "Title": "[BRQ] ...",
                    "Kbr": "Yes",
                    "MarketingTitleEn": "License management improvements for MSP/MSSP", // может быть null
                    "MarketingTitle": "Улучшения лицензирования для MSP/MSSP",           // обязательно
                    "Visibility": null,             // Only RU/RU, Only ENG/ENG, RU and ENG; null = обе версии
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

Правила: `Product/Stream/Tier/AppTitle` не переводятся (одно значение на оба языка). `Stream == "-"` → без Stream-divider слайда. `Tier.Releases == []` (или всё отфильтровано) → слайд для Tier не создаётся. Если у Product нет ни одного непустого Tier — весь Product (включая divider) пропускается. `Visibility`: `Only RU`/`RU` → только RU, `Only ENG`/`ENG` → только EN, `RU and ENG` → обе версии, `null`/отсутствие → обе версии. Неизвестное значение скрывает Requirement в обеих версиях и создаёт warning. `MarketingTitleEn == null` или пустая строка при EN-презентации → Requirement пропускается целиком в EN, остаётся в RU, если допускается `Visibility`.

### 2.2 Валидация

`validate_roadmap(data) -> list[str]` — собирает все ошибки за один проход, не бросает на первой. Проверки: `data` — непустой list; каждый Product/Stream/Tier — dict с обязательными строковыми полями; каждый Release — `Id` (int), `AppTitle`, `TrDate` (парсится); каждый Requirement — `Id` (int), `MarketingTitle` (непустая строка), `Kbr`/`MarketingTitleEn`/`IsSubjectToChange` опциональны (отсутствие — не ошибка, а warning + мягкий fallback: `Kbr` не задан → трактуется как не проходящий default-фильтр `Yes`; `IsSubjectToChange` не задан → `false`). Неуникальность `Id` НЕ является ошибкой — общий релиз/требование повторяется в разных Streams/Tiers (продакшен-выгрузка); это warning в `normalize_roadmap`.

## 3. Пользовательский сценарий

Загрузка JSON → выбор языка (RU/EN) → парсинг + normalize → применение глобального профиля плагинов и порядка (с попыткой матчинга по именам `(Product, Stream, Tier)` при переоткрытии проекта, см. раздел 8) → карточки-превью с diff-подсветкой → донастройка плагинов/порядка/переименований (мгновенный пересчёт `SlidePlan`, без рендера pptx) → "Сгенерировать pptx" → скачивание. Текущий JSON и UI-настройки автоматически сохраняются локально в браузере и восстанавливаются после refresh; пользователь может удалить этот контекст кнопкой "Очистить сессию". Опционально — "Сохранить проект" (экспорт переносимого JSON-бандла).

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

### 4.2 Tier-roadmap: колонки, группировка, упаковка

Алгоритм упаковки — канон из `Requirements/pptx_roadmap_TOR_v2.md` (базовая модель
«один шаблон + 4 фиксированных слота» с согласованным adaptive-fill исключением),
с зафиксированными решениями по открытым вопросам.

1. Собрать Requirements всех Releases тира, применить языковую видимость из `Visibility`, затем фильтр `kbr_filter` (по умолчанию: только `Kbr == "Yes"`); для EN — дополнительно отбросить отсутствующий/пустой `MarketingTitleEn`.
2. ????????????? ?????? ?? ???????????? ???????? `Qx YYYY`, ????????? ???????????? ???? (`CrDate`, ? ??? ?? ?????????? ? `TrDate`). ? JSON ? ????????????? ????? ???? ?????? ?? ????????? ???; ?????? ????? ?? ??????????? ?????????? ???? ? ???????? ??????, ?? ????????? ?????? ????? ??????? ???. ? ??????????? PPTX ???????? ?????? ???? ?????????? ????. ?????? ???????? ?? ?????????.
3. **Базовая геометрия слайда: ровно 4 логических слота.** Каждый квартал занимает 1..N слотов подряд; кварталы укладываются в свободные слоты слева направо (q1 → q4) и **никогда не разрываются частично** между слайдами — переносятся целиком, кроме случая «квартал больше целого слайда» (п.8). Если весь roadmap тира помещается на одном слайде и показан ровно один квартал, блок `col_bullets` занимает 50% доступной ширины и остаётся у левого края шаблона; заголовок квартала сохраняет свою ширину. Для 2–4 кварталов точки привязки колонок распределяются по ширине как 2 → 50/50, 3 → по 1/3, 4 → по 25%. При подколонках или continuation сохраняется базовая сетка 4×25%; одиночная колонка на слайде-продолжении использует всю ширину.
4. **Вместимость слота — динамическая**: высота ячейки фичи считается из длины текста (перенос строк по ширине слота; `chars_per_line` и `line_height` — из стилей эталонного шейпа-ячейки шаблона), а не фиксированным числом фич. Длинный текст переносится, высота строки растёт, вместимость слота соответственно падает.
5. Группировка по `AppTitle` внутри квартала (`apptitle_grouping`) — по умолчанию включена только для продуктов линии Next (по вхождению "Next" в `Product`), для остальных выключена; переключается вручную per-product. Порядок групп — по убыванию количества фич, либо по ручному глобальному приоритету AppTitle (`resolve_apptitle_order`), если задан. Заголовок группы = кастомное имя из `labels.get_apptitle_label`, иначе исходный `AppTitle`; показывается всегда. **Группа атомарна** — не рвётся между под-слотами; исключение (fallback): группа выше целого пустого слота разрывается построчно. Неконсекутивные вхождения одного `AppTitle` в квартале считаются **отдельными группами** (не сливаются).
   Aliases resolving to the same displayed label are merged into one group within each quarter before height-based packing; the merged group uses the position of its first source AppTitle in the resolved order.
6. Bullet-текст = `MarketingTitle`/`MarketingTitleEn`. Внутри группы — сначала `IsSubjectToChange == false`, затем `true` (помеченные `*`); если на слайде есть хоть один такой bullet — сноска внизу (текст в админке, 6.4).
7. **Заголовок квартала** показывается **только в первом под-слоте квартала**, у остальных под-слотов шапка пустая.
8. **Квартал больше целого слайда** (нужно >4 под-слотов) — растягивается на несколько слайдов подряд (по 4 слота на слайд, только этот квартал); на доп. слайдах показывается имя квартала.
9. **Слайд-продолжение** (переполнение) — содержит **только таблицу** (слоты), без заголовка роадмапа/легенды/`slide_title`.
10. Плагин `under_approval_badge` (project-scope, ручной, на уровне Release) — бейдж у первого под-слота соответствующего квартала.
11. Плагин `tier_inheritance_note` — если у Product в дереве порядка (4.3) включён флаг "Наследование", правило применяется ко всем Stream этого продукта в порядке дерева. Для каждого Tier, кроме самого первого Tier продукта, выводится синяя заметка "inc. all features of previous tier(s)"; каждый предшествующий Tier начинается с новой bullet-строки и перечисляется строго в последовательности презентации (`Stream / Tier`). Также выполняется **сквозная дедупликация по Product**: фичи, чей `Requirement.Id` уже показывался в любом предыдущем Tier любого Stream этого Product, на последующих слайдах НЕ дублируются. Если после дедупликации Tier пуст — его слайд не создаётся.

### 4.3 Ручной порядок слайдов (дерево, drag & drop)

Единое дерево на экране проектирования: `Product → Stream → Tier → Application (AppTitle-группа внутри Tier)`. Drag & drop только внутри одного родителя (нельзя переносить между разными Stream/Tier). Хранение — глобальный профиль, ключ = путь родителя, значение — упорядоченный список имён детей (`ordering.get_effective_order`/`save_order`). Новые узлы при перезагрузке JSON — в конец родителя, с diff-меткой "новое — проверьте позицию". Флаг "Наследование" (4.2 п.11) висит на узле Product и включает правило для всех его Stream; отдельного UI "Иерархия тиров" не существует.

Порядок Application (AppTitle) по умолчанию — авто по убыванию количества фич; ручной приоритет — **единый глобальный список** (`ordering.get_apptitle_priority`), не per-tier (см. допущение №3, раздел 14).

### 4.4 Переименование AppTitle

Глобальная map `{original_AppTitle: custom_label}` (`labels.py`), редактируется инлайн в карточке превью или в админке (раздел 6.5). Применяется по точному регистрозависимому совпадению. No-op, если `apptitle_grouping` выключена для продукта.

Aliases with identical effective display labels are rendered as one group; this also applies when a custom label matches an unmapped AppTitle.
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

- **7.1 Библиотека шаблонов**: карточки с PNG-превью первого слайда (конвейер `soffice`+`pdftoppm`), ошибки `validate_template_shapes` — красной рамкой на карточке со списком отсутствующих слотов. Один шаблон покрывает все случаи (вариант B: одна колонка-прототип + клонирование), поэтому выбор — просто `slide_type → файл` (выпадающий список, не код), без таблицы `columns × grouped`. Версионирование не требуется.
- **7.2 (упразднён)**: "Иерархия тиров" как отдельный UI не существует — заменена деревом порядка (4.3).
- **7.3 Статичные слайды**: библиотека готовых блоков (текст или скопированный `.pptx`-слайд) + точка вставки ("перед/после Product X", "в конце") — сохраняется в проекте.
- **7.4 Редактируемые строки**: RU/EN пары для сноски "Subject to Change", бейджа "Under approval", заголовка продолжения, шаблона фразы наследования тира.
- **7.5 Синонимы AppTitle**: таблица `Оригинал → Кастомное название`.
- **7.6 Приоритет AppTitle**: простой упорядочиваемый список (глобальный, см. 4.3).
- **7.7 Проверка ENG-названий фич**: в разделе «Отчёты» показывать блок только при выбранном ENG. Проверять только MarketingTitleEn каждого Requirement во всём текущем исходном JSON, независимо от года/TrDate и фильтров отчётов. Регистронезависимо искать отдельные слова ФСТЕК, ФСТЭК, FSTEC, FSB, ФСБ, СБЕР, SBER, Yandex, Яндекс, Astra, Астра; часть другого слова совпадением не считать. Каждое вхождение Requirement выводить отдельно с контекстом Product/Stream/Tier/Release, ReqId, английским заголовком и найденными словами; повторные ReqId не объединять. При отсутствии совпадений показывать пустое состояние.
- Однопользовательская, без разграничения прав.

## 8. Diff и повторное открытие проекта

Проектный файл = снимок JSON + язык + глобальный профиль плагинов/порядка/синонимов + per-product override + статичные слайды + ручные "under approval" + метаданные титула. При новой JSON: `match_previous_project` сопоставляет по именам `(Product, Stream, Tier)`, переносит override; несматченное — дефолты. `compute_diff` — по `Id` на уровне Release/Requirement. UI: зелёный бейдж "новое", жёлтый "изменено", приглушённый зачёркнутый "удалено" (секция под Tier, свёрнута по умолчанию), суммарный счётчик на родительском узле дерева.

## 9. Технологический стек

FastAPI + python-pptx + SQLite (backend), React+Vite+TypeScript (frontend), запуск `uvicorn` на localhost, Windows/Windows VM под macOS, только локальное хранилище, без обязательного офлайна, без авторизации, без ручного редактирования bullet-текста в превью (только выбор шаблонов/плагинов/порядка).

## 10. Визуальная точность (design fidelity)

- **Контракт именованных шейпов — данные, не код.** Состав обязательных и опциональных шейпов одного слайда-прототипа живёт в `config/template_contracts.yaml`, читается `template_registry.py`. Модель — **вариант B** («одна колонка-прототип»): builder сам клонирует `col_header`+`col_bullets` под каждый слот/квартал, поэтому отдельные слоты на комбинацию `columns × grouped` не нужны. Пример:
  ```yaml
  roadmap:
    base: [col_header, col_bullets]           # обязательные (прототип колонки)
    optional: [eyebrow, slide_title, col_group_header]
    roles:
      roadmap_label: [roadmap_label, roadmap]
      product_name: [Product_Name, product_name]
      quarter_marker: [quarter_marker, dot]
      product_logo: [product_logo, logo]
      tier_logo: [tier_logo, logo_tier]
      slide_number: [slide_number, number]
      subject_to_change_footnote: [subject_to_change_footnote, s2c]
      tier_inheritance_note: [tier_inheritance_note, inheritance_note]
  ```
  Изменение состава шейпов — правка только этого файла. **Поведение плейсхолдеров** (напр. `roadmap_label` — статичный текст, `subject_to_change_footnote` — сноска один раз, `slide_number` — порядковый номер, `product_logo` — подмена лого из библиотеки) зафиксировано в `builder.py`; канонические имена и legacy-алиасы ролей читаются из YAML.
- **Подстановка текста сохраняет форматирование**: замена содержимого именованного шейпа обязана наследовать шрифт/размер/цвет/жирность существующего run'а, не сбрасывать на дефолт python-pptx. В `col_bullets` первый абзац — прототип заголовка AppTitle, второй — прототип фичи; оба стиля независимо клонируются для любого числа групп.
- **Клонирование bullet-строк под переменное число фич** — через глубокое копирование XML-элемента параграфа (`copy.deepcopy` + `addnext`) — единственное официально допустимое исключение из правила AGENTS.md "не трогать приватные поля" python-pptx, т.к. библиотека не даёт публичного API клонирования.
- **Аннотации** (`subject_to_change_badge`, `under_approval_badge`, `tier_inheritance_note`) заполняют текстом заранее подготовленные, отформатированные, скрытые/пустые placeholder-шейпы шаблона — плагины никогда не выбирают цвет/шрифт в коде.
- **Логотипы** — два канонических плейсхолдера: `product_logo` (лого **продукта**, файл `data/img/product/logo/{slug}.png`) и `tier_logo` (лого **тира**, файл `data/img/tier/logo/{slug}.png`). Legacy-имена `logo`/`logo_tier` поддерживаются для совместимости. Если лого загружено — builder подменяет картинку, иначе оставляет как в шаблоне. Декоративная графика (`quarter_marker`, линии) — статичная часть шаблона.
- **Размер слайда** наследуется из загруженного шаблона (`prs.slide_width/height`), не переопределяется дефолтами python-pptx. Точки привязки слотов вычисляются из размера слайда; размеры `col_header`, `col_bullets` и относительное положение `quarter_marker` наследуются из шаблона.
- **Служебные/документационные слайды внутри multi-slide исходников** (например, слайд-памятка с описанием самих плейсхолдеров) — при нарезке `.pptx`-файла на шаблоны в админке помечаются вручную флагом "не использовать как шаблон".
- **Шрифт** — код не выбирает шрифт; всё, что "зашито" в форматирование шейпов шаблона, наследуется автоматически. Если позже понадобится гарантировать наличие конкретного корпоративного шрифта на машине рендера — это отдельная, не блокирующая v1 задача.

## 11. Тестовые данные и фикстуры

Реальный `product-tiers-data.json` содержит контент только для одного продукта (Kaspersky Next, 2 тира, 5 требований) — остальные продукты корректно дают пустой результат (подтверждает допущение №1), но **не покрывает** сценарии из Definition of Done. Обязательные синтетические фикстуры (`tests/fixtures/`):

- `quarter_overflow_many_features.json` — квартал с большим числом фич → проверка разбиения квартала на несколько под-слотов/слайдов и «заголовок только в первом под-слоте».
- `subject_to_change_mixed.json` — Requirements с `IsSubjectToChange: true` и `false` в одном квартале → проверка сортировки (false → true) и сноски.
- `non_next_product_flat.json` — продукт без "Next" в названии, несколько AppTitle → проверка, что группировка по умолчанию выключена (плоский список).
- `en_with_content.json` — Requirements с реально заполненным `MarketingTitleEn` (не null) → проверка, что EN-версия не пустая (текущий пример этого не доказывает, т.к. везде null).
- `missing_optional_fields.json` — часть Requirements без `Kbr`/`IsSubjectToChange` → проверка мягких fallback + warning, не ошибку.
- `tier_hierarchy_next.json` — Product со Stream, содержащим 2+ тира, и включённым флагом наследования → проверка `tier_inheritance_note`.

Тесты по реальному `product-tiers-data.json` остаются как "интеграционный smoke-тест на реальных данных", но не заменяют фикстуры выше.

## 12. Соглашение об именах шейпов и шаблон для разработки

`Roadmap_template.pptx` и `roadmap-orig-pptx.pptx` — **референсы дизайна**, не файлы для доработки/переименования шейпов. Финальный размеченный дизайн-шаблон приходит отдельно (design fidelity, раздел 10). Конвенция имён — **вариант B** («одна колонка-прототип»):

- **Обязательные**: `col_header` (прототип заголовка квартала), `col_bullets` (прототип списка фич).
- **Опциональные**: `eyebrow`, `slide_title`, `Product_Name` (название продукта; legacy `product_name`), `roadmap_label` (статичный ярлык), `product_logo`, `tier_logo`, `quarter_marker` (один прототип, клонируется над каждым `col_header`), `subject_to_change_footnote` (сноска один раз), `tier_inheritance_note` (каждый предыдущий Tier с новой строки), `slide_number` (порядковый номер слайда).
- **Служебные/направляющие** — с префиксом `_`; если имя после `_` совпадает с плейсхолдером или его legacy-алиасом — шейп обрабатывается билдером, иначе скрывается.

Полная таблица «плейсхолдер / описание / тип слайда», правила заполнения и чек-лист дизайнера находятся в `Requirements/template_placeholder_guide.md`.

Синтетический шаблон разработки (`tests/fixtures/synthetic_template.pptx`, генерируется через `python-pptx`) использует ту же конвенцию. Смена состава шейпов — правка `template_contracts.yaml`; код `template_registry.py`/`builder.py` при этом не меняется.

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
- [ ] Упаковка фич по TOR v2: базовая сетка из 4 фиксированных слотов + adaptive-fill для 1–3 простых колонок на единственном слайде, динамическая вместимость по высоте текста, атомарность групп, заголовок квартала только в первом под-слоте, слайд-продолжение = таблица.

## 15. Зафиксированные допущения

1. Product без непустых Tier — пропускается целиком (подтверждено на реальных данных).
2. Служебные RU-формулировки бейджей — дефолты в редактируемой таблице (7.4), не финальный текст.
3. Ручной приоритет AppTitle — единый глобальный список, не per-Tier/per-Product.
4. Новый узел дерева порядка — всегда в конец родителя, без эвристик по смыслу названия.
5. Шрифт не выбирается кодом — наследуется из форматирования шаблона; гарантия наличия конкретного корпоративного шрифта на машине рендера — вне scope v1.
6. `Roadmap_template.pptx`/`roadmap-orig-pptx.pptx` используются только как референс вёрстки для разработки логики, не как файлы для прямой доработки шейпов — финальный размеченный шаблон придёт отдельно.
7. Окно роадмапа — строго один год, 4 квартала (q1–q4); число кварталов не варьируется (TOR v2).
8. Вместимость слота — динамическая по высоте текста (TOR v2), не фиксированное число фич.
9. `Id` релиза/требования НЕ уникален глобально: общий релиз (и его Requirement) может повторяться в разных Streams/Tiers — это легитимная структура выгрузки, а не ошибка данных. `TrDate` приходит в одном из двух форматов (dot-24h или US-12h).
10. Наследование продукта (галка на Product в дереве) включает сквозную заметку и дедупликацию фич по `Requirement.Id` относительно всех предыдущих Tier всех Stream этого Product в порядке дерева.
