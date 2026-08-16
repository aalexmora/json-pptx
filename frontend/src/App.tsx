import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import type {
  Bullet,
  Column,
  DiffResponse,
  DividerSlide,
  LintIssue,
  PlanResponse,
  Profile,
  ReleaseInfo,
  RoadmapSlide,
  Slide,
  TemplateInfo,
  ThankYouSlide,
  TitleSlide,
  Tree,
} from './types'
import {
  downloadPptx,
  fetchDiff,
  fetchPlan,
  getProfile,
  listTemplates,
  saveProfile,
  setActiveTemplate,
  uploadTemplate,
} from './api'

const SAMPLE = JSON.stringify(
  [
    {
      Product: 'Kaspersky Next',
      Streams: [
        {
          Stream: 'Kaspersky Next Optimum',
          Tiers: [
            {
              Tier: 'Kaspersky Next EDR Foundations',
              Releases: [
                {
                  Id: 1,
                  Title: 'R1',
                  AppId: 1,
                  AppTitle: 'Managed Detection and Response',
                  TrDate: '15.01.2025 21:00:00',
                  Requirements: [
                    {
                      Id: 11,
                      Title: '[BRQ] A',
                      Kbr: 'Yes',
                      MarketingTitleEn: 'License management improvements',
                      MarketingTitle: 'Улучшения лицензирования',
                      IsSubjectToChange: false,
                    },
                    {
                      Id: 12,
                      Title: '[BRQ] B',
                      Kbr: 'Yes',
                      MarketingTitleEn: 'Android 16 support',
                      MarketingTitle: 'Поддержка Android 16',
                      IsSubjectToChange: true,
                    },
                  ],
                },
                {
                  Id: 2,
                  Title: 'R2',
                  AppId: 1,
                  AppTitle: 'Managed Detection and Response',
                  TrDate: '15.04.2025 21:00:00',
                  Requirements: [
                    {
                      Id: 21,
                      Title: '[BRQ] C',
                      Kbr: 'Yes',
                      MarketingTitleEn: 'Sandbox improvements',
                      MarketingTitle: 'Улучшения песочницы',
                      IsSubjectToChange: false,
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
  ],
  null,
  2,
)

const SERVICE_STRING_LABELS: Record<string, string> = {
  subject_to_change_footnote: 'Сноска «Subject to Change»',
  under_approval_badge: 'Бейдж «Под согласованием»',
  thank_you: 'Финальный слайд',
  inheritance_prefix: 'Фраза наследования тира',
  roadmap_title: 'Заголовок «Roadmap»',
  roadmap_cont_title: 'Заголовок продолжения',
}

function isDivider(slide: Slide): slide is DividerSlide {
  return 'divider_type' in slide
}

function isTitle(slide: Slide): slide is TitleSlide {
  return 'year' in slide && 'version' in slide
}

function isThankYou(slide: Slide): slide is ThankYouSlide {
  return 'text' in slide
}

function moveItem<T>(arr: T[], from: number, to: number): T[] {
  const next = [...arr]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

type DropHandlerFactory = (
  parentPath: string,
  index: number,
  siblings: string[],
) => {
  draggable: boolean
  onDragStart: () => void
  onDragOver: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
}

export default function App() {
  const [jsonText, setJsonText] = useState('')
  const [jsonData, setJsonData] = useState<unknown>(null)
  const [language, setLanguage] = useState<'ru' | 'en'>('ru')
  const [kbrEnabled, setKbrEnabled] = useState(true)
  const [apptitleMode, setApptitleMode] = useState<'auto' | 'on' | 'off'>('auto')
  const [result, setResult] = useState<PlanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() =>
    localStorage.getItem('theme') === 'dark' ? 'dark' : 'light',
  )
  const [profile, setProfile] = useState<Profile | null>(null)
  const [profileLoaded, setProfileLoaded] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const fileRef = useRef<HTMLInputElement>(null)
  const projectFileRef = useRef<HTMLInputElement>(null)
  const dragRef = useRef<{ parentPath: string; index: number } | null>(null)
  const [diff, setDiff] = useState<DiffResponse | null>(null)

  const newReqIds = useMemo(() => new Set(diff?.diff?.new_requirement_ids ?? []), [diff])
  const changedReqIds = useMemo(() => new Set(diff?.diff?.changed_requirement_ids ?? []), [diff])
  const newTierPaths = useMemo(() => new Set(diff?.new_tier_paths ?? []), [diff])
  const appTitles = useMemo(
    () => [...new Set((result?.releases ?? []).map((r) => r.app_title).filter(Boolean))],
    [result],
  )
  const productNames = useMemo(() => (result?.tree?.products ?? []).map((p) => p.name), [result])

  function buildSettings(): Record<string, unknown> {
    const global: Record<string, unknown> = {}
    if (!kbrEnabled) global.kbr_filter = { enabled: false }
    if (apptitleMode !== 'auto') global.apptitle_grouping = { enabled: apptitleMode === 'on' }
    return Object.keys(global).length ? { global } : {}
  }

  useEffect(() => {
    getProfile()
      .then((p) => setProfile(p))
      .catch(() => {})
      .finally(() => setProfileLoaded(true))
  }, [])

  useEffect(() => {
    if (!jsonData || !profileLoaded) return
    let cancelled = false
    setLoading(true)
    fetchPlan(jsonData, language, buildSettings())
      .then((res) => {
        if (cancelled) return
        setResult(res)
        setError(res.errors.length ? res.errors.join('; ') : null)
      })
      .catch((e) => {
        if (!cancelled) setError(String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [jsonData, language, kbrEnabled, apptitleMode, refreshKey, profileLoaded])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  function loadData(data: unknown) {
    if (jsonData) {
      fetchDiff(jsonData, data, language)
        .then(setDiff)
        .catch(() => setDiff(null))
    } else {
      setDiff(null)
    }
    setJsonData(data)
  }

  function handleLoad() {
    try {
      loadData(JSON.parse(jsonText))
    } catch {
      setError('Некорректный JSON')
    }
  }

  function handleSample() {
    setJsonText(SAMPLE)
    loadData(JSON.parse(SAMPLE))
  }

  function handleFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      try {
        const text = String(reader.result)
        setJsonText(text)
        loadData(JSON.parse(text))
        setError(null)
      } catch {
        setError('Файл не является корректным JSON')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  function handleExport() {
    if (!jsonData || !profile) return
    const project = { version: 1, json_data: jsonData, language, profile }
    const blob = new Blob([JSON.stringify(project, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'roadmap-project.json'
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleImportProject(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = async () => {
      try {
        const project = JSON.parse(String(reader.result))
        const data = project.json_data
        const lang = project.language === 'en' ? 'en' : 'ru'
        setJsonText(JSON.stringify(data, null, 2))
        setLanguage(lang)
        setDiff(null)
        if (project.profile) {
          await saveProfile(project.profile)
          setProfile(project.profile)
        }
        setJsonData(data)
      } catch {
        setError('Файл не является корректным проектом')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  function toggleTheme() {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }

  async function handleGenerate() {
    if (!jsonData) return
    try {
      await downloadPptx(jsonData, language, buildSettings())
    } catch (e) {
      setError('Ошибка генерации: ' + e)
    }
  }

  async function persist(next: Profile) {
    setProfile(next)
    await saveProfile(next)
    setRefreshKey((k) => k + 1)
  }

  function handleReorder(parentPath: string, names: string[]) {
    if (!profile) return
    persist({
      ...profile,
      ordering: { ...profile.ordering, order: { ...profile.ordering.order, [parentPath]: names } },
    })
  }

  function handleToggleInheritance(tierPath: string, flag: boolean) {
    if (!profile) return
    persist({
      ...profile,
      ordering: {
        ...profile.ordering,
        tier_inheritance_flags: { ...profile.ordering.tier_inheritance_flags, [tierPath]: flag },
      },
    })
  }

  function handleToggleApproval(releaseId: number, approved: boolean) {
    if (!profile) return
    const ids = new Set(profile.under_approval_ids)
    if (approved) ids.add(releaseId)
    else ids.delete(releaseId)
    persist({ ...profile, under_approval_ids: [...ids].sort((a, b) => a - b) })
  }

  function handleDeckMeta(field: 'title' | 'year' | 'version', value: string) {
    if (!profile) return
    persist({ ...profile, deck_meta: { ...profile.deck_meta, [field]: value } })
  }

  function handleServiceString(key: string, lang: 'ru' | 'en', value: string) {
    if (!profile) return
    persist({
      ...profile,
      service_strings: {
        ...profile.service_strings,
        [key]: { ...profile.service_strings[key], [lang]: value },
      },
    })
  }

  function handleLabel(original: string, custom: string) {
    if (!profile) return
    const labels = { ...profile.labels }
    if (custom.trim() === '') delete labels[original]
    else labels[original] = custom
    persist({ ...profile, labels })
  }

  function handlePriority(names: string[]) {
    if (!profile) return
    persist({ ...profile, ordering: { ...profile.ordering, apptitle_priority: names } })
  }

  function handleStaticSlides(slides: { title: string; text: string; position: string }[]) {
    if (!profile) return
    persist({ ...profile, static_slides: slides })
  }

  const dropHandlers: DropHandlerFactory = (parentPath, index, siblings) => ({
    draggable: true,
    onDragStart: () => {
      dragRef.current = { parentPath, index }
    },
    onDragOver: (e) => {
      e.preventDefault()
      e.stopPropagation()
    },
    onDrop: (e) => {
      e.preventDefault()
      e.stopPropagation()
      const d = dragRef.current
      if (!d || d.parentPath !== parentPath || d.index === index) return
      handleReorder(parentPath, moveItem(siblings, d.index, index))
      dragRef.current = null
    },
  })

  return (
    <div className="layout">
      <header className="header">
        <h1>Roadmap → PPTX</h1>
        <div className="header-actions">
          <button onClick={toggleTheme} title="Переключить тему">
            {theme === 'dark' ? '☀️ Светлая' : '🌙 Ночная'}
          </button>
          <button onClick={handleGenerate} disabled={!jsonData}>
            Сгенерировать PPTX
          </button>
        </div>
      </header>

      <aside className="sidebar">
        <input
          ref={fileRef}
          type="file"
          accept=".json,application/json"
          style={{ display: 'none' }}
          onChange={handleFile}
        />
        <input
          ref={projectFileRef}
          type="file"
          accept=".json,application/json"
          style={{ display: 'none' }}
          onChange={handleImportProject}
        />
        <div className="controls">
          <button onClick={handleSample}>Загрузить пример</button>
          <button onClick={() => fileRef.current?.click()}>Загрузить JSON из файла</button>
          <button onClick={handleExport} disabled={!jsonData}>
            Сохранить проект
          </button>
          <button onClick={() => projectFileRef.current?.click()}>Загрузить проект</button>
          <label>
            Язык:
            <select value={language} onChange={(e) => setLanguage(e.target.value as 'ru' | 'en')}>
              <option value="ru">RU</option>
              <option value="en">EN</option>
            </select>
          </label>
          <label>
            <input type="checkbox" checked={kbrEnabled} onChange={(e) => setKbrEnabled(e.target.checked)} />
            KBR-фильтр (только Yes)
          </label>
          <label>
            Группировка по AppTitle:
            <select
              value={apptitleMode}
              onChange={(e) => setApptitleMode(e.target.value as 'auto' | 'on' | 'off')}
            >
              <option value="auto">Авто (только Next)</option>
              <option value="on">Вкл для всех</option>
              <option value="off">Выкл для всех</option>
            </select>
          </label>
          <div className="deck-meta">
            <span className="deck-meta-title">Титульный слайд</span>
            <input
              type="text"
              placeholder="Заголовок"
              value={profile?.deck_meta?.title ?? ''}
              onChange={(e) => handleDeckMeta('title', e.target.value)}
            />
            <div className="deck-meta-row">
              <input
                type="text"
                placeholder="Год"
                value={profile?.deck_meta?.year ?? ''}
                onChange={(e) => handleDeckMeta('year', e.target.value)}
              />
              <input
                type="text"
                placeholder="Версия"
                value={profile?.deck_meta?.version ?? ''}
                onChange={(e) => handleDeckMeta('version', e.target.value)}
              />
            </div>
          </div>
        </div>

        <textarea
          className="json-input"
          placeholder="Вставьте JSON-выгрузку roadmap…"
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
        />
        <button onClick={handleLoad} disabled={loading}>
          Обновить превью
        </button>

        {error && <div className="error">{error}</div>}
      </aside>

      <main className="content">
        {loading && <p>Загрузка…</p>}
        {result && result.lint_issues.length > 0 && (
          <div className="lint">
            <h3>Ошибки линтера ({result.lint_issues.length})</h3>
            {result.lint_issues.map((issue, i) => (
              <LintRow key={i} issue={issue} />
            ))}
          </div>
        )}

        {result && result.tree && profile && (
          <details className="section" open>
            <summary>Дерево порядка слайдов</summary>
            <TreeView
              tree={result.tree}
              dropHandlers={dropHandlers}
              onToggleInheritance={handleToggleInheritance}
              newTierPaths={newTierPaths}
            />
          </details>
        )}

        {result && (result.releases ?? []).length > 0 && profile && (
          <details className="section">
            <summary>Под согласованием</summary>
            <ApprovalList
              releases={result.releases}
              approvedIds={profile.under_approval_ids}
              onToggle={handleToggleApproval}
            />
          </details>
        )}

        {profile && profile.service_strings && (
          <details className="section">
            <summary>Служебные строки (RU/EN)</summary>
            <ServiceStringsPanel strings={profile.service_strings} onChange={handleServiceString} />
          </details>
        )}

        {profile && (
          <details className="section">
            <summary>Синонимы AppTitle</summary>
            <SynonymsPanel labels={profile.labels} appTitles={appTitles} onChange={handleLabel} />
          </details>
        )}

        {profile && (
          <details className="section">
            <summary>Приоритет AppTitle</summary>
            <PriorityPanel
              priority={profile.ordering.apptitle_priority}
              appTitles={appTitles}
              onChange={handlePriority}
            />
          </details>
        )}

        {profile && (
          <details className="section">
            <summary>Статичные слайды</summary>
            <StaticSlidesPanel
              slides={profile.static_slides ?? []}
              productNames={productNames}
              onChange={handleStaticSlides}
            />
          </details>
        )}

        <details className="section">
          <summary>Библиотека шаблонов</summary>
          <TemplatesPanel />
        </details>

        {diff && diff.diff && (
          <div className="diff-summary">
            <b>Изменения относительно прошлой загрузки:</b>{' '}
            +{diff.diff.new_requirement_ids?.length ?? 0} новых,{' '}
            ~{diff.diff.changed_requirement_ids?.length ?? 0} изменено,{' '}
            −{diff.diff.removed_requirement_ids?.length ?? 0} удалено
          </div>
        )}

        {result && result.plan && (
          <div className="slides">
            {result.plan.slides.map((slide, i) => (
              <SlideCard key={i} slide={slide} newReqIds={newReqIds} changedReqIds={changedReqIds} />
            ))}
          </div>
        )}
      </main>
    </div>
  )
}

function LintRow({ issue }: { issue: LintIssue }) {
  return (
    <div className="lint-item">
      <b>{issue.message}</b>
      <div className="lint-text">«{issue.text}» — {issue.tier} (req {issue.requirement_id})</div>
    </div>
  )
}

function TreeView({
  tree,
  dropHandlers,
  onToggleInheritance,
  newTierPaths,
}: {
  tree: Tree
  dropHandlers: DropHandlerFactory
  onToggleInheritance: (tierPath: string, flag: boolean) => void
  newTierPaths: Set<string>
}) {
  return (
    <div className="tree">
      {tree.products.map((p, i) => (
        <div
          key={p.name}
          {...dropHandlers('', i, tree.products.map((x) => x.name))}
          className="tree-node product"
        >
          <span className="tree-label">{p.name}</span>
          <div className="tree-children">
            {p.streams.map((s, si) => (
              <div
                key={s.name}
                {...dropHandlers(p.name, si, p.streams.map((x) => x.name))}
                className="tree-node stream"
              >
                <span className="tree-label">{s.name}</span>
                <div className="tree-children">
                  {s.tiers.map((t, ti) => (
                    <div
                      key={t.name}
                      {...dropHandlers(`${p.name} > ${s.name}`, ti, s.tiers.map((x) => x.name))}
                      className="tree-node tier"
                    >
                      <span className="tree-label">{t.name}</span>
                      {newTierPaths.has(`${p.name} > ${s.name} > ${t.name}`) && (
                        <span className="tree-badge">новое</span>
                      )}
                      <label className="inheritance-check">
                        <input
                          type="checkbox"
                          checked={t.inheritance_flag}
                          onChange={(e) =>
                            onToggleInheritance(`${p.name} > ${s.name} > ${t.name}`, e.target.checked)
                          }
                        />
                        наследование
                      </label>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ApprovalList({
  releases,
  approvedIds,
  onToggle,
}: {
  releases: ReleaseInfo[]
  approvedIds: number[]
  onToggle: (releaseId: number, approved: boolean) => void
}) {
  const approved = new Set(approvedIds)
  return (
    <div className="approval-list">
      {releases.map((r) => (
        <label key={r.id} className="approval-item">
          <input type="checkbox" checked={approved.has(r.id)} onChange={(e) => onToggle(r.id, e.target.checked)} />
          <span>
            {r.app_title || r.title} · {r.quarter}
          </span>
        </label>
      ))}
    </div>
  )
}

function ServiceStringsPanel({
  strings,
  onChange,
}: {
  strings: Record<string, { ru: string; en: string }>
  onChange: (key: string, lang: 'ru' | 'en', value: string) => void
}) {
  return (
    <div className="service-strings">
      {Object.entries(strings).map(([key, langs]) => (
        <div key={key} className="service-row">
          <div className="service-label">{SERVICE_STRING_LABELS[key] ?? key}</div>
          <input
            type="text"
            value={langs.ru}
            placeholder="RU"
            onChange={(e) => onChange(key, 'ru', e.target.value)}
          />
          <input
            type="text"
            value={langs.en}
            placeholder="EN"
            onChange={(e) => onChange(key, 'en', e.target.value)}
          />
        </div>
      ))}
    </div>
  )
}

function SynonymsPanel({
  labels,
  appTitles,
  onChange,
}: {
  labels: Record<string, string>
  appTitles: string[]
  onChange: (original: string, custom: string) => void
}) {
  const [orig, setOrig] = useState('')
  const [custom, setCustom] = useState('')

  function add() {
    if (!orig.trim()) return
    onChange(orig.trim(), custom)
    setOrig('')
    setCustom('')
  }

  return (
    <div className="synonyms">
      {Object.entries(labels).map(([o, c]) => (
        <div key={o} className="synonym-row">
          <span className="synonym-orig">{o}</span>
          <input type="text" value={c} placeholder="Кастомное название" onChange={(e) => onChange(o, e.target.value)} />
          <button onClick={() => onChange(o, '')}>✕</button>
        </div>
      ))}
      <div className="synonym-row">
        <input type="text" list="apptitle-syn" value={orig} placeholder="Оригинал" onChange={(e) => setOrig(e.target.value)} />
        <input type="text" value={custom} placeholder="Кастомное название" onChange={(e) => setCustom(e.target.value)} />
        <button onClick={add}>+</button>
      </div>
      <datalist id="apptitle-syn">
        {appTitles.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </div>
  )
}

function PriorityPanel({
  priority,
  appTitles,
  onChange,
}: {
  priority: string[]
  appTitles: string[]
  onChange: (names: string[]) => void
}) {
  const [name, setName] = useState('')

  function move(i: number, dir: -1 | 1) {
    const j = i + dir
    if (j < 0 || j >= priority.length) return
    const next = [...priority]
    const [x] = next.splice(i, 1)
    next.splice(j, 0, x)
    onChange(next)
  }

  function add() {
    const n = name.trim()
    if (!n || priority.includes(n)) return
    onChange([...priority, n])
    setName('')
  }

  return (
    <div className="priority">
      {priority.length === 0 && <div className="priority-empty">Приоритет не задан — группы по числу фич.</div>}
      {priority.map((n, i) => (
        <div key={n} className="priority-row">
          <span className="priority-name">{n}</span>
          <button onClick={() => move(i, -1)}>↑</button>
          <button onClick={() => move(i, 1)}>↓</button>
          <button onClick={() => onChange(priority.filter((_, k) => k !== i))}>✕</button>
        </div>
      ))}
      <div className="priority-row">
        <input type="text" list="apptitle-prio" value={name} placeholder="AppTitle" onChange={(e) => setName(e.target.value)} />
        <button onClick={add}>+</button>
      </div>
      <datalist id="apptitle-prio">
        {appTitles.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </div>
  )
}

function StaticSlidesPanel({
  slides,
  productNames,
  onChange,
}: {
  slides: { title: string; text: string; position: string }[]
  productNames: string[]
  onChange: (slides: { title: string; text: string; position: string }[]) => void
}) {
  const positions = ['end', ...productNames.flatMap((p) => [`before:${p}`, `after:${p}`])]

  function update(i: number, patch: Partial<{ title: string; text: string; position: string }>) {
    onChange(slides.map((s, k) => (k === i ? { ...s, ...patch } : s)))
  }

  return (
    <div className="static-slides">
      {slides.map((s, i) => (
        <div key={i} className="static-row">
          <input type="text" value={s.title} placeholder="Заголовок" onChange={(e) => update(i, { title: e.target.value })} />
          <input type="text" value={s.text} placeholder="Текст" onChange={(e) => update(i, { text: e.target.value })} />
          <select value={s.position} onChange={(e) => update(i, { position: e.target.value })}>
            {positions.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <button onClick={() => onChange(slides.filter((_, k) => k !== i))}>✕</button>
        </div>
      ))}
      <button onClick={() => onChange([...slides, { title: '', text: '', position: 'end' }])}>
        + Добавить статичный слайд
      </button>
    </div>
  )
}

function TemplatesPanel() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function refresh() {
    try {
      setTemplates(await listTemplates())
    } catch {
      setTemplates([])
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  async function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      await uploadTemplate(file)
      await refresh()
    } catch (err) {
      alert('Ошибка загрузки шаблона: ' + err)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function activate(filename: string | null) {
    await setActiveTemplate(filename)
    await refresh()
  }

  return (
    <div className="templates">
      <input ref={fileRef} type="file" accept=".pptx" style={{ display: 'none' }} onChange={onFile} />
      <button onClick={() => fileRef.current?.click()} disabled={uploading}>
        {uploading ? 'Загрузка…' : 'Загрузить шаблон (.pptx)'}
      </button>
      <div className="templates-list">
        {templates.map((t) => (
          <div key={t.filename} className="template-item">
            {t.preview && <img src={`/api/templates/preview/${t.filename}`} alt="" className="template-preview" />}
            <div className="template-meta">
              <div className="template-name">
                {t.filename}
                {t.active && <span className="badge">Активен</span>}
              </div>
              {t.valid ? (
                <div className="template-ok">✓ все шейпы на месте</div>
              ) : (
                <div className="template-err">отсутствуют: {t.missing_shapes.join(', ')}</div>
              )}
            </div>
            {!t.active && <button onClick={() => activate(t.filename)}>Сделать активным</button>}
          </div>
        ))}
        {templates.length === 0 && (
          <div className="template-empty">Шаблоны не загружены — используется синтетический.</div>
        )}
      </div>
    </div>
  )
}

function SlideCard({
  slide,
  newReqIds,
  changedReqIds,
}: {
  slide: Slide
  newReqIds: Set<number>
  changedReqIds: Set<number>
}) {
  if (isTitle(slide)) {
    return (
      <div className="card divider divider-title">
        <span className="badge">TITLE</span>
        <span className="divider-title">{slide.title || 'Roadmap'}</span>
        {(slide.year || slide.version) && (
          <span className="title-sub">{[slide.year, slide.version].filter(Boolean).join(' ')}</span>
        )}
      </div>
    )
  }
  if (isThankYou(slide)) {
    return (
      <div className="card divider divider-thankyou">
        <span className="divider-title">{slide.text}</span>
      </div>
    )
  }
  if (isDivider(slide)) {
    return (
      <div className={'card divider divider-' + slide.divider_type}>
        <span className="badge">{slide.divider_type.toUpperCase()}</span>
        <span className="divider-title">{slide.title}</span>
      </div>
    )
  }
  return <RoadmapCard slide={slide} newReqIds={newReqIds} changedReqIds={changedReqIds} />
}

function RoadmapCard({
  slide,
  newReqIds,
  changedReqIds,
}: {
  slide: RoadmapSlide
  newReqIds: Set<number>
  changedReqIds: Set<number>
}) {
  return (
    <div className="card roadmap">
      <div className="roadmap-head">
        <span className="badge">{slide.continuation ? 'Roadmap (cont.)' : 'Roadmap'}</span>
        <span className="tier">{slide.tier}</span>
      </div>
      {slide.inheritance_note && <div className="inheritance">{slide.inheritance_note}</div>}
      <div className="columns">
        {slide.columns.map((col, i) => (
          <ColumnView key={i} col={col} newReqIds={newReqIds} changedReqIds={changedReqIds} />
        ))}
      </div>
      {slide.footnote && <div className="footnote">{slide.footnote}</div>}
    </div>
  )
}

function ColumnView({
  col,
  newReqIds,
  changedReqIds,
}: {
  col: Column
  newReqIds: Set<number>
  changedReqIds: Set<number>
}) {
  const bullets = col.grouped
    ? col.groups.flatMap((g) => g.bullets.map((b) => ({ b, group: g.app_title })))
    : col.bullets.map((b) => ({ b, group: null as string | null }))

  let lastGroup: string | null = null
  return (
    <div className="column">
      <div className="quarter">{col.quarter}</div>
      {col.under_approval_badge && <div className="approval-badge">{col.under_approval_badge}</div>}
      {bullets.map(({ b, group }, i) => {
        const showHeader = group !== null && group !== lastGroup
        lastGroup = group
        return (
          <div key={i}>
            {showHeader && <div className="group-header">{group}</div>}
            <BulletView
              b={b}
              isNew={newReqIds.has(b.requirement_id)}
              isChanged={changedReqIds.has(b.requirement_id)}
            />
          </div>
        )
      })}
    </div>
  )
}

function BulletView({ b, isNew, isChanged }: { b: Bullet; isNew: boolean; isChanged: boolean }) {
  return (
    <div className={'bullet' + (b.is_subject_to_change ? ' stc' : '')}>
      {b.text}
      {b.is_subject_to_change && <span className="star"> *</span>}
      {isNew && <span className="diff-badge new">новое</span>}
      {isChanged && <span className="diff-badge changed">изменено</span>}
    </div>
  )
}
