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
  StaticSlide,
  TemplateInfo,
  ThankYouSlide,
  TitleSlide,
  Tree,
} from './types'
import {
  deleteTemplate,
  downloadPptx,
  fetchDiff,
  fetchPlan,
  getProfile,
  listTemplates,
  saveProfile,
  setActiveTemplate,
  uploadStaticSlidePptx,
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

function isStatic(slide: Slide): slide is StaticSlide {
  return 'pptx' in slide
}

function computeInsertPoints(slides: Slide[]): { index: number; position: string }[] {
  const points: { index: number; position: string }[] = []
  let thankYouIndex = -1
  slides.forEach((s, i) => {
    if (isDivider(s) && s.divider_type === 'product') {
      points.push({ index: i, position: `before:${s.title}` })
    }
    if (isThankYou(s) && thankYouIndex === -1) thankYouIndex = i
  })
  points.push({ index: thankYouIndex >= 0 ? thankYouIndex : slides.length, position: 'end' })
  return points.sort((a, b) => a.index - b.index)
}

interface TierNode {
  tier: string
  slides: RoadmapSlide[]
}
interface StreamNode {
  stream: string
  tiers: TierNode[]
}
interface ProductNode {
  product: string
  streams: StreamNode[]
}

function groupSlides(slides: Slide[]): { top: Slide[]; products: ProductNode[] } {
  const top: Slide[] = []
  const products: ProductNode[] = []
  const prodIndex = new Map<string, ProductNode>()
  const streamIndex = new Map<string, StreamNode>()

  for (const s of slides) {
    if (isTitle(s) || isThankYou(s) || isStatic(s)) {
      top.push(s)
      continue
    }
    if (isDivider(s)) continue // разделители подразумеваются группировкой
    const r = s as RoadmapSlide
    let prod = prodIndex.get(r.product)
    if (!prod) {
      prod = { product: r.product, streams: [] }
      products.push(prod)
      prodIndex.set(r.product, prod)
    }
    const streamKey = r.product + '||' + r.stream
    let stream = streamIndex.get(streamKey)
    if (!stream) {
      stream = { stream: r.stream, tiers: [] }
      prod.streams.push(stream)
      streamIndex.set(streamKey, stream)
    }
    const last = stream.tiers[stream.tiers.length - 1]
    if (last && last.tier === r.tier) last.slides.push(r)
    else stream.tiers.push({ tier: r.tier, slides: [r] })
  }
  return { top, products }
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
  onDragStart: (e: DragEvent) => void
  onDragOver: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
}

export default function App() {
  const [jsonText, setJsonText] = useState('')
  const [jsonData, setJsonData] = useState<unknown>(null)
  const [language, setLanguage] = useState<'ru' | 'en'>('ru')
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
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [rightWidth, setRightWidth] = useState(320)
  const [collapsedSlides, setCollapsedSlides] = useState<Set<number>>(new Set())
  const [staticModal, setStaticModal] = useState({ open: false, name: '', position: 'end', pptx: '' })

  const newReqIds = useMemo(() => new Set(diff?.diff?.new_requirement_ids ?? []), [diff])
  const changedReqIds = useMemo(() => new Set(diff?.diff?.changed_requirement_ids ?? []), [diff])
  const newTierPaths = useMemo(() => new Set(diff?.new_tier_paths ?? []), [diff])
  const appTitles = useMemo(
    () => [...new Set((result?.releases ?? []).map((r) => r.app_title).filter(Boolean))],
    [result],
  )
  const productNames = useMemo(() => (result?.tree?.products ?? []).map((p) => p.name), [result])

  const slideItems = useMemo(() => {
    const slides = result?.plan?.slides ?? []
    const ptAt = new Map(computeInsertPoints(slides).map((p) => [p.index, p.position]))
    const items: ({ kind: 'marker'; position: string } | { kind: 'slide'; slide: Slide; index: number })[] = []
    slides.forEach((slide, i) => {
      const pos = ptAt.get(i)
      if (pos !== undefined) items.push({ kind: 'marker', position: pos })
      items.push({ kind: 'slide', slide, index: i })
    })
    const endPos = ptAt.get(slides.length)
    if (endPos !== undefined) items.push({ kind: 'marker', position: endPos })
    return items
  }, [result])

  function buildSettings(): Record<string, unknown> {
    const global: Record<string, unknown> = {}
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
  }, [jsonData, language, apptitleMode, refreshKey, profileLoaded])

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

  const saveQueue = useRef<Promise<void>>(Promise.resolve())

  async function persist(next: Profile) {
    setProfile(next)
    // сериализуем сохранения, чтобы backend не получил устаревший профиль при быстрых правках
    const save = saveQueue.current.then(() => saveProfile(next))
    saveQueue.current = save
    await save
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

  function toggleSlide(i: number) {
    setCollapsedSlides((prev) => {
      const next = new Set(prev)
      if (next.has(i)) next.delete(i)
      else next.add(i)
      return next
    })
  }

  function toggleAllSlides(total: number) {
    setCollapsedSlides((prev) =>
      prev.size > 0 ? new Set() : new Set(Array.from({ length: total }, (_, i) => i)),
    )
  }

  function openStaticSlideModal(position = 'end') {
    setStaticModal({ open: true, name: '', position, pptx: '' })
  }

  function handleDeleteStaticSlide(index: number) {
    if (!profile) return
    handleStaticSlides((profile.static_slides ?? []).filter((_, k) => k !== index))
  }

  function closeStaticSlideModal() {
    setStaticModal((m) => ({ ...m, open: false }))
  }

  function submitStaticSlide() {
    if (!profile) return
    handleStaticSlides([
      ...(profile.static_slides ?? []),
      { name: staticModal.name, position: staticModal.position, pptx: staticModal.pptx },
    ])
    closeStaticSlideModal()
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

  function handleStaticSlides(slides: { name: string; position: string; pptx: string }[]) {
    if (!profile) return
    persist({ ...profile, static_slides: slides })
  }

  function handleProductLanguage(name: string, lang: 'ru' | 'en', visible: boolean) {
    if (!profile) return
    const current = profile.product_languages?.[name] ?? { ru: true, en: true }
    persist({
      ...profile,
      product_languages: { ...profile.product_languages, [name]: { ...current, [lang]: visible } },
    })
  }

  const dropHandlers: DropHandlerFactory = (parentPath, index, siblings) => ({
    draggable: true,
    onDragStart: (e) => {
      dragRef.current = { parentPath, index }
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', String(index))
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
    <div
      className="layout"
      style={{
        gridTemplateColumns: `${leftCollapsed ? '0px' : '280px'} minmax(0, 1fr) ${
          rightCollapsed ? '0px' : rightWidth + 'px'
        }`,
      }}
    >
      <header className="header">
        <div className="header-left">
          <button onClick={() => setLeftCollapsed((v) => !v)} title="Скрыть/показать меню данных">
            {leftCollapsed ? '☰' : '✕'}
          </button>
          <h1>Roadmap → PPTX</h1>
        </div>
        <div className="header-actions">
          <button onClick={toggleTheme} title="Переключить тему">
            {theme === 'dark' ? '☀️ Светлая' : '🌙 Ночная'}
          </button>
          <button onClick={() => setRightCollapsed((v) => !v)} title="Скрыть/показать настройки">
            {rightCollapsed ? '⚙' : '✕'}
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
        </div>

        <details className="json-debug">
          <summary>JSON (debug)</summary>
          <textarea
            className="json-input"
            placeholder="Вставьте JSON-выгрузку roadmap…"
            value={jsonText}
            onChange={(e) => setJsonText(e.target.value)}
          />
          <button onClick={handleLoad} disabled={loading}>
            Обновить превью
          </button>
        </details>

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
          <>
            <div className="slides-toolbar">
              <button onClick={() => toggleAllSlides(result.plan!.slides.length)}>
                {collapsedSlides.size > 0 ? 'Раскрыть все блоки' : 'Схлопнуть все блоки'}
              </button>
              <button onClick={() => openStaticSlideModal()}>＋ Статичный слайд</button>
            </div>
            <div className="slides">
              <GroupedSlides
                slides={result.plan.slides}
                dropHandlers={dropHandlers}
                newReqIds={newReqIds}
                changedReqIds={changedReqIds}
                collapsedSlides={collapsedSlides}
                toggleSlide={toggleSlide}
                tierInheritanceFlags={profile?.ordering.tier_inheritance_flags ?? {}}
                onToggleInheritance={handleToggleInheritance}
                newTierPaths={newTierPaths}
                productLanguages={profile?.product_languages ?? {}}
              />
            </div>
          </>
        )}
      </main>

      <aside className="right-panel">
        <div
          className="resize-handle"
          onMouseDown={(e) => {
            e.preventDefault()
            const startX = e.clientX
            const startWidth = rightWidth
            const onMove = (ev: MouseEvent) =>
              setRightWidth(Math.max(240, Math.min(600, startWidth + (startX - ev.clientX))))
            const onUp = () => {
              window.removeEventListener('mousemove', onMove)
              window.removeEventListener('mouseup', onUp)
            }
            window.addEventListener('mousemove', onMove)
            window.addEventListener('mouseup', onUp)
          }}
        />
        <div className="controls">
          <label>
            Язык:
            <select value={language} onChange={(e) => setLanguage(e.target.value as 'ru' | 'en')}>
              <option value="ru">RU</option>
              <option value="en">EN</option>
            </select>
          </label>
        </div>

        {profile && productNames.length > 0 && (
          <details className="section">
            <summary>Языки продуктов</summary>
            <ProductLanguagesPanel
              productNames={productNames}
              languages={profile.product_languages ?? {}}
              onChange={handleProductLanguage}
            />
          </details>
        )}

        {profile && (
          <details className="section">
            <summary>Статичные слайды</summary>
            <StaticSlidesList slides={profile.static_slides ?? []} onDelete={handleDeleteStaticSlide} />
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

        {profile && (
          <details className="section">
            <summary>App group mapping</summary>
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

        <div className="controls">
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

        {profile && profile.service_strings && (
          <details className="section">
            <summary>Служебные строки (RU/EN)</summary>
            <ServiceStringsPanel strings={profile.service_strings} onChange={handleServiceString} />
          </details>
        )}
      </aside>

      <StaticSlideModal
        modal={staticModal}
        productNames={productNames}
        onChange={(patch) => setStaticModal((m) => ({ ...m, ...patch }))}
        onClose={closeStaticSlideModal}
        onSubmit={submitStaticSlide}
      />
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
                      {ti > 0 && (
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
                      )}
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
        <select value={orig} onChange={(e) => setOrig(e.target.value)}>
          <option value="">— выберите AppTitle —</option>
          {appTitles.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <input type="text" value={custom} placeholder="Кастомное название" onChange={(e) => setCustom(e.target.value)} />
        <button onClick={add}>+</button>
      </div>
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
        <select value={name} onChange={(e) => setName(e.target.value)}>
          <option value="">— выберите AppTitle —</option>
          {appTitles.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button onClick={add}>+</button>
      </div>
    </div>
  )
}

function StaticSlideModal({
  modal,
  productNames,
  onChange,
  onClose,
  onSubmit,
}: {
  modal: { open: boolean; name: string; position: string; pptx: string }
  productNames: string[]
  onChange: (patch: Partial<{ name: string; position: string; pptx: string }>) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const positions = ['end', ...productNames.flatMap((p) => [`before:${p}`, `after:${p}`])]

  async function upload(file: File) {
    try {
      const { filename, extracted_title } = await uploadStaticSlidePptx(file)
      const patch: { pptx: string; name?: string } = { pptx: filename }
      if (!modal.name.trim()) patch.name = extracted_title
      onChange(patch)
    } catch (err) {
      alert('Ошибка загрузки: ' + err)
    }
  }

  if (!modal.open) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>Новый статичный слайд</h3>
        <label className="modal-field">
          Название:
          <input type="text" value={modal.name} onChange={(e) => onChange({ name: e.target.value })} />
        </label>
        <label className="modal-field">
          Позиция:
          <select value={modal.position} onChange={(e) => onChange({ position: e.target.value })}>
            {positions.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
        <div
          className={'dropzone' + (dragOver ? ' over' : '')}
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setDragOver(false)
            const file = e.dataTransfer.files?.[0]
            if (file) upload(file)
          }}
        >
          {modal.pptx ? `📎 ${modal.pptx}` : 'Перетащите .pptx сюда или кликните для выбора'}
          <input
            ref={fileRef}
            type="file"
            accept=".pptx"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) upload(f)
              e.target.value = ''
            }}
          />
        </div>
        <div className="modal-actions">
          <button onClick={onClose}>Отмена</button>
          <button onClick={onSubmit}>Добавить</button>
        </div>
      </div>
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

  async function remove(filename: string) {
    if (!window.confirm(`Удалить шаблон «${filename}»?`)) return
    try {
      await deleteTemplate(filename)
      await refresh()
    } catch (err) {
      alert('Ошибка удаления: ' + err)
    }
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
              {(t.issues ?? []).length > 0 ? (
                <div className="template-err">
                  {(t.issues ?? []).map((msg, i) => (
                    <div key={i}>{msg}</div>
                  ))}
                </div>
              ) : (
                <div className="template-ok">✓ все шейпы на месте</div>
              )}
            </div>
            {!t.active && <button onClick={() => activate(t.filename)}>Сделать активным</button>}
            <button className="danger" onClick={() => remove(t.filename)}>Удалить</button>
          </div>
        ))}
        {templates.length === 0 && (
          <div className="template-empty">Шаблоны не загружены — используется синтетический.</div>
        )}
      </div>
    </div>
  )
}

function InsertMarker({ position, onInsert }: { position: string; onInsert: (position: string) => void }) {
  return (
    <div className="insert-marker" onClick={() => onInsert(position)} title={`Вставить сюда (${position})`}>
      <span className="insert-plus">＋</span>
    </div>
  )
}

function StaticSlidesList({
  slides,
  onDelete,
}: {
  slides: { name: string; position: string; pptx: string }[]
  onDelete: (index: number) => void
}) {
  if (slides.length === 0) return <div className="priority-empty">Нет статичных слайдов.</div>
  return (
    <div className="static-list">
      {slides.map((s, i) => (
        <div key={i} className="static-list-row">
          <span className="static-list-name">{s.name || '(без названия)'}</span>
          <span className="static-list-pos">{s.position}</span>
          <button title="Удалить" onClick={() => onDelete(i)}>
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}

function GroupedSlides({
  slides,
  dropHandlers,
  newReqIds,
  changedReqIds,
  collapsedSlides,
  toggleSlide,
  tierInheritanceFlags,
  onToggleInheritance,
  newTierPaths,
  productLanguages,
}: {
  slides: Slide[]
  dropHandlers: DropHandlerFactory
  newReqIds: Set<number>
  changedReqIds: Set<number>
  collapsedSlides: Set<number>
  toggleSlide: (i: number) => void
  tierInheritanceFlags: Record<string, boolean>
  onToggleInheritance: (tierPath: string, flag: boolean) => void
  newTierPaths: Set<string>
  productLanguages: Record<string, { ru: boolean; en: boolean }>
}) {
  const { top, products } = groupSlides(slides)

  const langLabel = (name: string): string | null => {
    const l = productLanguages[name] ?? { ru: true, en: true }
    if (!l.ru && !l.en) return 'скрыт'
    if (!l.ru) return 'только EN'
    if (!l.en) return 'только RU'
    return null
  }

  const card = (s: Slide, idx: number, collapsible: boolean) => (
    <SlideCard
      key={idx}
      slide={s}
      newReqIds={newReqIds}
      changedReqIds={changedReqIds}
      expanded={collapsible ? !collapsedSlides.has(idx) : true}
      onToggle={collapsible ? () => toggleSlide(idx) : () => {}}
    />
  )

  return (
    <div className="grouped">
      {top.filter(isTitle).map((s) => card(s, slides.indexOf(s), false))}
      {products.map((p) => (
        <div key={p.product} className="group">
          <div
            {...dropHandlers('', products.indexOf(p), products.map((x) => x.product))}
            className="group-header product-h"
          >
            <span className="badge">PRODUCT</span>
            <span className="group-title">{p.product}</span>
            {langLabel(p.product) && <span className="lang-badge">{langLabel(p.product)}</span>}
          </div>
          {p.streams.map((st) => (
            <div key={st.stream} className="group">
              {st.stream !== '-' && (
                <div
                  {...dropHandlers(p.product, p.streams.indexOf(st), p.streams.map((x) => x.stream))}
                  className="group-header stream-h"
                >
                  <span className="badge">STREAM</span>
                  <span className="group-title">{st.stream}</span>
                </div>
              )}
              {st.tiers.map((t, ti) => (
                <div key={t.tier} className="group">
                  <div
                    {...dropHandlers(
                      `${p.product} > ${st.stream}`,
                      ti,
                      st.tiers.map((x) => x.tier),
                    )}
                    className="group-header tier-h"
                  >
                    <span className="badge">TIER</span>
                    <span className="group-title">{t.tier}</span>
                    {newTierPaths.has(`${p.product} > ${st.stream} > ${t.tier}`) && (
                      <span className="tree-badge">новое</span>
                    )}
                    {ti > 0 && (
                      <label className="inheritance-check">
                        <input
                          type="checkbox"
                          checked={!!tierInheritanceFlags[`${p.product} > ${st.stream} > ${t.tier}`]}
                          onChange={(e) =>
                            onToggleInheritance(`${p.product} > ${st.stream} > ${t.tier}`, e.target.checked)
                          }
                        />
                        наследование
                      </label>
                    )}
                  </div>
                  {t.slides.map((r) => card(r, slides.indexOf(r), true))}
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
      {top.filter(isStatic).map((s) => card(s, slides.indexOf(s), false))}
      {top.filter(isThankYou).map((s) => card(s, slides.indexOf(s), false))}
    </div>
  )
}

function ProductLanguagesPanel({
  productNames,
  languages,
  onChange,
}: {
  productNames: string[]
  languages: Record<string, { ru: boolean; en: boolean }>
  onChange: (name: string, lang: 'ru' | 'en', visible: boolean) => void
}) {
  return (
    <div className="product-langs">
      {productNames.map((name) => {
        const l = languages[name] ?? { ru: true, en: true }
        return (
          <div key={name} className="product-lang-row">
            <span className="product-lang-name">{name}</span>
            <button className={'lang-chip' + (l.ru ? ' on' : '')} onClick={() => onChange(name, 'ru', !l.ru)}>
              RU
            </button>
            <button className={'lang-chip' + (l.en ? ' on' : '')} onClick={() => onChange(name, 'en', !l.en)}>
              EN
            </button>
          </div>
        )
      })}
    </div>
  )
}

function SlideCard({
  slide,
  newReqIds,
  changedReqIds,
  expanded,
  onToggle,
}: {
  slide: Slide
  newReqIds: Set<number>
  changedReqIds: Set<number>
  expanded: boolean
  onToggle: () => void
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
  if (isStatic(slide)) {
    return (
      <div className="card divider divider-static">
        <span className="badge">STATIC</span>
        <span className="divider-title">{slide.name || '(без названия)'}</span>
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
  return (
    <RoadmapCard
      slide={slide}
      newReqIds={newReqIds}
      changedReqIds={changedReqIds}
      expanded={expanded}
      onToggle={onToggle}
    />
  )
}

function RoadmapCard({
  slide,
  newReqIds,
  changedReqIds,
  expanded,
  onToggle,
}: {
  slide: RoadmapSlide
  newReqIds: Set<number>
  changedReqIds: Set<number>
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className="card roadmap" onClick={onToggle}>
      <div className="roadmap-head">
        <span className="badge">{slide.continuation ? 'Roadmap (cont.)' : 'Roadmap'}</span>
        <span className="tier">{slide.tier}</span>
        <span className="collapse-hint">{expanded ? '▾' : '▸'}</span>
      </div>
      {expanded && slide.inheritance_note && <div className="inheritance">{slide.inheritance_note}</div>}
      {expanded && (
        <div className="columns">
          {slide.columns.map((col, i) => (
            <ColumnView key={i} col={col} newReqIds={newReqIds} changedReqIds={changedReqIds} />
          ))}
        </div>
      )}
      {expanded && slide.footnote && <div className="footnote">{slide.footnote}</div>}
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
