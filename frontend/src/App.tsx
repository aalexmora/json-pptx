import { useEffect, useMemo, useRef, useState, type ChangeEvent, type DragEvent, type KeyboardEvent as ReactKeyboardEvent } from 'react'
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
  deleteProductLogo,
  deleteTemplate,
  deleteTierLogo,
  downloadPptx,
  fetchDiff,
  fetchHealth,
  fetchPlan,
  getProductLogoStatuses,
  getProfile,
  getTierLogoStatuses,
  listTemplates,
  saveProfile,
  setActiveTemplate,
  uploadProductLogo,
  uploadStaticSlidePptx,
  uploadTemplate,
  uploadTierLogo,
  type ProductLogoStatus,
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

type SaveState = 'idle' | 'saving' | 'saved' | 'error'
type AppTitleMode = 'auto' | 'on' | 'off'

const WORKSPACE_SESSION_KEY = 'roadmap-pptx.workspace.v1'

interface WorkspaceSession {
  version: 1
  jsonData: unknown
  jsonText: string
  language: 'ru' | 'en'
  apptitleMode: AppTitleMode
  leftCollapsed: boolean
  rightCollapsed: boolean
  rightWidth: number
  collapsedSlides: number[]
}

function readWorkspaceSession(): WorkspaceSession | null {
  try {
    const raw = localStorage.getItem(WORKSPACE_SESSION_KEY)
    if (!raw) return null
    const saved = JSON.parse(raw) as Record<string, unknown>
    if (saved.version !== 1) return null
    const language = saved.language === 'en' ? 'en' : 'ru'
    const apptitleMode: AppTitleMode =
      saved.apptitleMode === 'on' || saved.apptitleMode === 'off' ? saved.apptitleMode : 'auto'
    const rightWidth = typeof saved.rightWidth === 'number'
      ? Math.max(240, Math.min(600, saved.rightWidth))
      : 320
    return {
      version: 1,
      jsonData: saved.jsonData ?? null,
      jsonText: typeof saved.jsonText === 'string' ? saved.jsonText : '',
      language,
      apptitleMode,
      leftCollapsed: saved.leftCollapsed === true,
      rightCollapsed: saved.rightCollapsed === true,
      rightWidth,
      collapsedSlides: Array.isArray(saved.collapsedSlides)
        ? saved.collapsedSlides.filter((item): item is number => Number.isInteger(item) && item >= 0)
        : [],
    }
  } catch {
    localStorage.removeItem(WORKSPACE_SESSION_KEY)
    return null
  }
}

function positionLabel(position: string): string {
  if (position === 'end') return 'В конце презентации'
  if (position.startsWith('before:')) return `Перед продуктом «${position.slice(7)}»`
  if (position.startsWith('after:')) return `После продукта «${position.slice(6)}»`
  return position
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

function groupSlides(slides: Slide[], tree: Tree | null): { top: Slide[]; products: ProductNode[] } {
  const top: Slide[] = []
  const slidesByTier = new Map<string, RoadmapSlide[]>()

  const tierKey = (product: string, stream: string, tier: string) =>
    JSON.stringify([product, stream, tier])

  for (const slide of slides) {
    if (isTitle(slide) || isThankYou(slide) || isStatic(slide)) {
      top.push(slide)
    } else if (!isDivider(slide)) {
      const roadmapSlide = slide as RoadmapSlide
      const key = tierKey(roadmapSlide.product, roadmapSlide.stream, roadmapSlide.tier)
      const tierSlides = slidesByTier.get(key) ?? []
      tierSlides.push(roadmapSlide)
      slidesByTier.set(key, tierSlides)
    }
  }

  // Дерево API — единственный источник порядка узлов. Пустые узлы (Tier/Stream/
  // Product без единой фичи после фильтрации, дедупликации или скрытия языка)
  // в среднее окно не выводятся — как и в build_slide_plan, где им не создаётся
  // слайд. Фильтруем только рендер: полный `tree` остаётся источником списков
  // продуктов/тиров для правой панели (логотипы, языки), иначе скрытый продукт
  // нельзя было бы вернуть.
  if (tree) {
    const products = tree.products
      .map((product) => ({
        product: product.name,
        streams: product.streams
          .map((stream) => ({
            stream: stream.name,
            tiers: stream.tiers
              .map((tier) => ({
                tier: tier.name,
                slides: slidesByTier.get(tierKey(product.name, stream.name, tier.name)) ?? [],
              }))
              .filter((tier) => tier.slides.length > 0),
          }))
          .filter((stream) => stream.tiers.length > 0),
      }))
      .filter((product) => product.streams.length > 0)
    return { top, products }
  }

  const products: ProductNode[] = []
  const prodIndex = new Map<string, ProductNode>()
  const streamIndex = new Map<string, StreamNode>()

  for (const slide of slides) {
    if (isTitle(slide) || isThankYou(slide) || isStatic(slide) || isDivider(slide)) continue

    const roadmapSlide = slide as RoadmapSlide
    let product = prodIndex.get(roadmapSlide.product)
    if (!product) {
      product = { product: roadmapSlide.product, streams: [] }
      products.push(product)
      prodIndex.set(roadmapSlide.product, product)
    }

    const streamKey = `${roadmapSlide.product}||${roadmapSlide.stream}`
    let stream = streamIndex.get(streamKey)
    if (!stream) {
      stream = { stream: roadmapSlide.stream, tiers: [] }
      product.streams.push(stream)
      streamIndex.set(streamKey, stream)
    }

    const lastTier = stream.tiers[stream.tiers.length - 1]
    if (lastTier && lastTier.tier === roadmapSlide.tier) {
      lastTier.slides.push(roadmapSlide)
    } else {
      stream.tiers.push({ tier: roadmapSlide.tier, slides: [roadmapSlide] })
    }
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
  tabIndex: number
  role: 'button'
  'aria-label': string
  onDragStart: (e: DragEvent) => void
  onDragEnd: (e: DragEvent) => void
  onDragOver: (e: DragEvent) => void
  onDragLeave: (e: DragEvent) => void
  onDrop: (e: DragEvent) => void
  onKeyDown: (e: ReactKeyboardEvent) => void
}

export default function App() {
  const [restoredSession] = useState<WorkspaceSession | null>(() => readWorkspaceSession())
  const [jsonText, setJsonText] = useState(restoredSession?.jsonText ?? '')
  const [jsonData, setJsonData] = useState<unknown>(restoredSession?.jsonData ?? null)
  const [language, setLanguage] = useState<'ru' | 'en'>(restoredSession?.language ?? 'ru')
  const [apptitleMode, setApptitleMode] = useState<AppTitleMode>(restoredSession?.apptitleMode ?? 'auto')
  const [result, setResult] = useState<PlanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [appVersion, setAppVersion] = useState('')
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
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
  const [leftCollapsed, setLeftCollapsed] = useState(restoredSession?.leftCollapsed ?? false)
  const [rightCollapsed, setRightCollapsed] = useState(restoredSession?.rightCollapsed ?? false)
  const [rightWidth, setRightWidth] = useState(restoredSession?.rightWidth ?? 320)
  const [collapsedSlides, setCollapsedSlides] = useState<Set<number>>(
    () => new Set(restoredSession?.collapsedSlides ?? []),
  )
  const [staticModal, setStaticModal] = useState({ open: false, name: '', position: 'end', pptx: '' })
  const [logoStatus, setLogoStatus] = useState<Record<string, ProductLogoStatus>>({})
  const [logoRefresh, setLogoRefresh] = useState(0)
  const [tierLogoStatus, setTierLogoStatus] = useState<Record<string, ProductLogoStatus>>({})
  const [tierLogoRefresh, setTierLogoRefresh] = useState(0)
  const saveTimerRef = useRef<number | null>(null)
  const pendingProfileRef = useRef<Profile | null>(null)

  const newReqIds = useMemo(() => new Set(diff?.diff?.new_requirement_ids ?? []), [diff])
  const changedReqIds = useMemo(() => new Set(diff?.diff?.changed_requirement_ids ?? []), [diff])
  const newTierPaths = useMemo(() => new Set(diff?.new_tier_paths ?? []), [diff])
  const appTitles = useMemo(
    () => [...new Set((result?.releases ?? []).map((r) => r.app_title).filter(Boolean))],
    [result],
  )
  const productNames = useMemo(() => (result?.tree?.products ?? []).map((p) => p.name), [result])
  const tierNames = useMemo(
    () => (result?.tree?.products ?? []).flatMap((p) => p.streams.flatMap((s) => s.tiers.map((t) => t.name))),
    [result],
  )

  // Статус логотипов продуктов обновляется при смене списка продуктов и после
  // загрузки/удаления лого (logoRefresh). Сами файлы живут на бэке (data/img/…).
  useEffect(() => {
    if (!productNames.length) return
    let alive = true
    getProductLogoStatuses(productNames)
      .then((statuses) => {
        if (alive) setLogoStatus(statuses)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [productNames, logoRefresh])

  // Статус логотипов тиров.
  useEffect(() => {
    if (!tierNames.length) return
    let alive = true
    getTierLogoStatuses(tierNames)
      .then((statuses) => {
        if (alive) setTierLogoStatus(statuses)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [tierNames, tierLogoRefresh])

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
    fetchHealth()
      .then((h) => setAppVersion(h.version))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!jsonData || !profileLoaded) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchPlan(jsonData, language, buildSettings())
      .then((res) => {
        if (cancelled) return
        setResult(res)
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

  useEffect(() => {
    const session: WorkspaceSession = {
      version: 1,
      jsonData,
      jsonText,
      language,
      apptitleMode,
      leftCollapsed,
      rightCollapsed,
      rightWidth,
      collapsedSlides: [...collapsedSlides],
    }
    try {
      localStorage.setItem(WORKSPACE_SESSION_KEY, JSON.stringify(session))
    } catch {
      setError('Не удалось сохранить рабочую сессию в браузере: возможно, JSON слишком большой.')
    }
  }, [jsonData, jsonText, language, apptitleMode, leftCollapsed, rightCollapsed, rightWidth, collapsedSlides])

  useEffect(() => {
    const compact = window.matchMedia('(max-width: 900px)')
    const collapsePanels = (event: MediaQueryListEvent | MediaQueryList) => {
      if (event.matches) {
        setLeftCollapsed(true)
        setRightCollapsed(true)
      }
    }
    collapsePanels(compact)
    compact.addEventListener('change', collapsePanels)
    return () => compact.removeEventListener('change', collapsePanels)
  }, [])

  useEffect(
    () => () => {
      if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    },
    [],
  )

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
    const project = { version: 2, json_data: jsonData, language, apptitle_mode: apptitleMode, profile }
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
        const groupingMode: AppTitleMode =
          project.apptitle_mode === 'on' || project.apptitle_mode === 'off' ? project.apptitle_mode : 'auto'
        setJsonText(JSON.stringify(data, null, 2))
        setLanguage(lang)
        setApptitleMode(groupingMode)
        setDiff(null)
        if (project.profile) {
          await saveProfile(project.profile)
          // Backend нормализует старые профили (Tier-флаги → Product-флаги).
          // Возвращаем нормализованное состояние в UI сразу, без перезагрузки.
          setProfile(await getProfile())
        }
        setJsonData(data)
      } catch {
        setError('Файл не является корректным проектом')
      }
    }
    reader.readAsText(file)
    e.target.value = ''
  }

  function handleClearSession() {
    if (!window.confirm('Удалить загруженный JSON и очистить текущее превью? Глобальные настройки сохранятся.')) {
      return
    }
    localStorage.removeItem(WORKSPACE_SESSION_KEY)
    setJsonText('')
    setJsonData(null)
    setResult(null)
    setDiff(null)
    setError(null)
    setNotice(null)
    setCollapsedSlides(new Set())
  }

  function toggleTheme() {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }

  async function handleGenerate() {
    if (!jsonData) return
    setGenerating(true)
    setNotice(null)
    try {
      await flushPendingProfile()
      await downloadPptx(jsonData, language, buildSettings())
      setNotice('Презентация готова и скачана.')
    } catch (e) {
      setError('Ошибка генерации: ' + e)
    } finally {
      setGenerating(false)
    }
  }

  const saveQueue = useRef<Promise<void>>(Promise.resolve())

  async function commitProfile(next: Profile) {
    const save = saveQueue.current.catch(() => undefined).then(() => saveProfile(next))
    saveQueue.current = save
    try {
      await save
      if (pendingProfileRef.current === null) {
        setSaveState('saved')
        setRefreshKey((k) => k + 1)
      } else {
        setSaveState('saving')
      }
    } catch {
      setSaveState('error')
      setError('Не удалось сохранить настройки профиля.')
      throw new Error('profile save failed')
    }
  }

  function persist(next: Profile) {
    setProfile(next)
    pendingProfileRef.current = next
    setSaveState('saving')
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = window.setTimeout(() => {
      const pending = pendingProfileRef.current
      pendingProfileRef.current = null
      saveTimerRef.current = null
      if (pending) void commitProfile(pending).catch(() => undefined)
    }, 400)
  }

  async function flushPendingProfile() {
    if (saveTimerRef.current !== null) window.clearTimeout(saveTimerRef.current)
    saveTimerRef.current = null
    const pending = pendingProfileRef.current
    pendingProfileRef.current = null
    if (pending) await commitProfile(pending)
  }

  function handleReorder(parentPath: string, names: string[]) {
    if (!profile) return
    persist({
      ...profile,
      ordering: { ...profile.ordering, order: { ...profile.ordering.order, [parentPath]: names } },
    })
  }

  function handleToggleInheritance(productName: string, flag: boolean) {
    if (!profile) return
    persist({
      ...profile,
      ordering: {
        ...profile.ordering,
        product_inheritance_flags: {
          ...profile.ordering.product_inheritance_flags,
          [productName]: flag,
        },
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

  function handleUploadLogo(name: string, file: File) {
    uploadProductLogo(name, file)
      .then(() => setLogoRefresh((n) => n + 1))
      .catch(() => setError('Не удалось загрузить логотип продукта.'))
  }

  function handleDeleteLogo(name: string) {
    deleteProductLogo(name)
      .then(() => setLogoRefresh((n) => n + 1))
      .catch(() => setError('Не удалось удалить логотип продукта.'))
  }

  function handleUploadTierLogo(name: string, file: File) {
    uploadTierLogo(name, file)
      .then(() => setTierLogoRefresh((n) => n + 1))
      .catch(() => setError('Не удалось загрузить логотип тира.'))
  }

  function handleDeleteTierLogo(name: string) {
    deleteTierLogo(name)
      .then(() => setTierLogoRefresh((n) => n + 1))
      .catch(() => setError('Не удалось удалить логотип тира.'))
  }

  const dropHandlers: DropHandlerFactory = (parentPath, index, siblings) => ({
    draggable: true,
    tabIndex: 0,
    role: 'button',
    'aria-label': `${siblings[index]}. Перетаскивание внутри текущей группы. Alt и стрелки меняют порядок.`,
    onDragStart: (e) => {
      e.stopPropagation()
      dragRef.current = { parentPath, index }
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', String(index))
      e.currentTarget.classList.add('dragging')
    },
    onDragEnd: (e) => {
      e.stopPropagation()
      e.currentTarget.classList.remove('dragging')
      dragRef.current = null
    },
    onDragOver: (e) => {
      e.preventDefault()
      e.stopPropagation()
      e.currentTarget.classList.add('drag-over')
    },
    onDragLeave: (e) => {
      e.stopPropagation()
      e.currentTarget.classList.remove('drag-over')
    },
    onDrop: (e) => {
      e.preventDefault()
      e.stopPropagation()
      e.currentTarget.classList.remove('drag-over')
      const d = dragRef.current
      if (!d || d.parentPath !== parentPath || d.index === index) return
      handleReorder(parentPath, moveItem(siblings, d.index, index))
      dragRef.current = null
    },
    onKeyDown: (e) => {
      if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return
      e.preventDefault()
      e.stopPropagation()
      const target = e.key === 'ArrowUp' ? index - 1 : index + 1
      if (target >= 0 && target < siblings.length) handleReorder(parentPath, moveItem(siblings, index, target))
    },
  })

  const planErrors = result?.errors ?? []
  const planWarnings = result?.warnings ?? []
  const planConflicts = result?.plan?.conflicts ?? []
  const lintIssues = result?.lint_issues ?? []
  const qualityCount = planErrors.length + planWarnings.length + planConflicts.length + lintIssues.length
  const slideCount = result?.plan?.slides.length ?? 0
  const canGenerate = Boolean(jsonData && result?.plan && planErrors.length === 0 && !loading && !generating)

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
          <button
            className="icon-button"
            onClick={() => {
              if (leftCollapsed && window.innerWidth <= 900) setRightCollapsed(true)
              setLeftCollapsed((v) => !v)
            }}
            title="Скрыть или показать панель данных"
            aria-label="Скрыть или показать панель данных"
            aria-expanded={!leftCollapsed}
          >
            {leftCollapsed ? '☰' : '‹'}
          </button>
          <div className="brand">
            <h1>Roadmap → PPTX</h1>
            <span>Конструктор презентаций</span>
          </div>
          {appVersion && <span className="app-version" title="Версия приложения">v{appVersion}</span>}
        </div>
        <div className="header-actions">
          {Boolean(jsonData) && (
            <span className={'status-pill ' + (planErrors.length ? 'error' : qualityCount ? 'warning' : 'success')}>
              {loading ? 'Проверяем…' : planErrors.length ? 'Есть ошибки' : qualityCount ? `${qualityCount} замеч.` : 'Готово'}
            </span>
          )}
          {saveState !== 'idle' && (
            <span className={'save-state ' + saveState} role="status">
              {saveState === 'saving' && 'Сохранение…'}
              {saveState === 'saved' && 'Сохранено'}
              {saveState === 'error' && 'Ошибка сохранения'}
            </span>
          )}
          <div className="language-switch" aria-label="Язык презентации">
            <button className={language === 'ru' ? 'active' : ''} onClick={() => setLanguage('ru')} aria-pressed={language === 'ru'}>RU</button>
            <button className={language === 'en' ? 'active' : ''} onClick={() => setLanguage('en')} aria-pressed={language === 'en'}>EN</button>
          </div>
          <button className="icon-button" onClick={toggleTheme} title="Переключить тему" aria-label="Переключить тему">
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <button
            className="icon-button"
            onClick={() => {
              if (rightCollapsed && window.innerWidth <= 900) setLeftCollapsed(true)
              setRightCollapsed((v) => !v)
            }}
            title="Скрыть или показать инспектор"
            aria-label="Скрыть или показать инспектор"
            aria-expanded={!rightCollapsed}
          >
            {rightCollapsed ? '⚙' : '›'}
          </button>
          <button className="primary-button" onClick={handleGenerate} disabled={!canGenerate}>
            {generating ? 'Генерация…' : 'Скачать PPTX'}
          </button>
        </div>
      </header>

      <aside className={'sidebar' + (leftCollapsed ? ' is-collapsed' : '')} aria-hidden={leftCollapsed}>
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
        <div className="panel-heading">
          <span className="eyebrow">Шаг 1</span>
          <h2>Исходные данные</h2>
          <p>Загрузите JSON-выгрузку или продолжите работу с сохранённым проектом.</p>
        </div>

        <div className={'source-status' + (jsonData ? ' loaded' : '')}>
          <span className="source-status-icon">{jsonData ? '✓' : '↑'}</span>
          <div>
            <strong>{jsonData ? 'Данные загружены' : 'Roadmap JSON'}</strong>
            <span>{jsonData ? `${productNames.length} продукт(а), ${slideCount} слайд(а)` : 'Формат .json'}</span>
          </div>
        </div>

        <div className="controls project-actions">
          <button className="primary-button" onClick={() => fileRef.current?.click()}>Загрузить JSON</button>
          <button onClick={handleSample}>Использовать пример</button>
        </div>

        <div className="sidebar-divider" />
        <div className="sidebar-label">Проект</div>
        <div className="controls compact-actions">
          <button onClick={() => projectFileRef.current?.click()}>Открыть проект</button>
          <button onClick={handleExport} disabled={!jsonData}>Сохранить проект</button>
          <button className="danger" onClick={handleClearSession} disabled={!jsonData && !jsonText}>
            Очистить сессию
          </button>
        </div>

        <details className="json-debug">
          <summary>Редактировать исходный JSON</summary>
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

      </aside>

      <main className="content">
        {error && <div className="error">{error}</div>}
        {!jsonData ? (
          <div className="preview-placeholder">
            <h2>Превью презентации</h2>
            <p>Здесь появится структура будущей презентации</p>
          </div>
        ) : (
          <>
            {loading && <p>Загрузка…</p>}
            {notice && <div className="message success-message" role="status"><strong>Готово</strong><span>{notice}</span></div>}
            {result && result.lint_issues.length > 0 && (
              <div className="lint">
                <h3>Ошибки линтера ({result.lint_issues.length})</h3>
                {result.lint_issues.map((issue, index) => (
                  <LintRow key={index} issue={issue} />
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
                    tree={result.tree}
                    dropHandlers={dropHandlers}
                    newReqIds={newReqIds}
                    changedReqIds={changedReqIds}
                    collapsedSlides={collapsedSlides}
                    toggleSlide={toggleSlide}
                    productInheritanceFlags={profile?.ordering.product_inheritance_flags ?? {}}
                    onToggleInheritance={handleToggleInheritance}
                    newTierPaths={newTierPaths}
                    productLanguages={profile?.product_languages ?? {}}
                  />
                </div>
              </>
            )}
          </>
        )}
      </main>

      <aside className={'right-panel' + (rightCollapsed ? ' is-collapsed' : '')} aria-hidden={rightCollapsed}>
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

        {profile && productNames.length > 0 && (
          <details className="section">
            <summary>Логотипы продуктов</summary>
            <ProductLogosPanel
              productNames={productNames}
              statuses={logoStatus}
              onUpload={handleUploadLogo}
              onDelete={handleDeleteLogo}
            />
          </details>
        )}

        {profile && tierNames.length > 0 && (
          <details className="section">
            <summary>Логотипы тиров</summary>
            <ProductLogosPanel
              productNames={tierNames}
              statuses={tierLogoStatus}
              onUpload={handleUploadTierLogo}
              onDelete={handleDeleteTierLogo}
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
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const positions = ['end', ...productNames.flatMap((p) => [`before:${p}`, `after:${p}`])]

  useEffect(() => {
    if (!modal.open) return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [modal.open, onClose])

  async function upload(file: File) {
    setUploadError(null)
    try {
      const { filename, extracted_title } = await uploadStaticSlidePptx(file)
      const patch: { pptx: string; name?: string } = { pptx: filename }
      if (!modal.name.trim()) patch.name = extracted_title
      onChange(patch)
    } catch (err) {
      setUploadError('Не удалось загрузить слайд: ' + err)
    }
  }

  if (!modal.open) return null

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-labelledby="static-slide-title" onClick={(e) => e.stopPropagation()}>
        <h3 id="static-slide-title">Новый статичный слайд</h3>
        <label className="modal-field">
          Название:
          <input autoFocus type="text" value={modal.name} onChange={(e) => onChange({ name: e.target.value })} />
        </label>
        <label className="modal-field">
          Позиция:
          <select value={modal.position} onChange={(e) => onChange({ position: e.target.value })}>
            {positions.map((p) => (
              <option key={p} value={p}>
                {positionLabel(p)}
              </option>
            ))}
          </select>
        </label>
        <div
          className={'dropzone' + (dragOver ? ' over' : '')}
          role="button"
          tabIndex={0}
          onClick={() => fileRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') fileRef.current?.click()
          }}
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
        {uploadError && <div className="error" role="alert">{uploadError}</div>}
        <div className="modal-actions">
          <button onClick={onClose}>Отмена</button>
          <button className="primary-button" onClick={onSubmit} disabled={!modal.pptx}>Добавить</button>
        </div>
      </div>
    </div>
  )
}

function TemplatesPanel() {
  const [templates, setTemplates] = useState<TemplateInfo[]>([])
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
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
      setMessage('Шаблон загружен.')
    } catch (err) {
      setMessage('Ошибка загрузки шаблона: ' + err)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  async function activate(filename: string | null) {
    await setActiveTemplate(filename)
    await refresh()
    setMessage('Активный шаблон изменён.')
  }

  async function remove(filename: string) {
    if (!window.confirm(`Удалить шаблон «${filename}»?`)) return
    try {
      await deleteTemplate(filename)
      await refresh()
      setMessage('Шаблон удалён.')
    } catch (err) {
      setMessage('Ошибка удаления: ' + err)
    }
  }

  return (
    <div className="templates">
      <input ref={fileRef} type="file" accept=".pptx" style={{ display: 'none' }} onChange={onFile} />
      <button onClick={() => fileRef.current?.click()} disabled={uploading}>
        {uploading ? 'Загрузка…' : 'Загрузить шаблон (.pptx)'}
      </button>
      {message && <div className="inline-message" role="status">{message}</div>}
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
    <button className="insert-marker" onClick={() => onInsert(position)} title={positionLabel(position)} aria-label={`Добавить статичный слайд: ${positionLabel(position)}`}>
      <span className="insert-plus">＋</span>
      <span className="insert-label">Добавить слайд</span>
    </button>
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
  tree,
  dropHandlers,
  newReqIds,
  changedReqIds,
  collapsedSlides,
  toggleSlide,
  productInheritanceFlags,
  onToggleInheritance,
  newTierPaths,
  productLanguages,
}: {
  slides: Slide[]
  tree: Tree | null
  dropHandlers: DropHandlerFactory
  newReqIds: Set<number>
  changedReqIds: Set<number>
  collapsedSlides: Set<number>
  toggleSlide: (index: number) => void
  productInheritanceFlags: Record<string, boolean>
  onToggleInheritance: (productName: string, flag: boolean) => void
  newTierPaths: Set<string>
  productLanguages: Record<string, { ru: boolean; en: boolean }>
}) {
  const { top, products } = groupSlides(slides, tree)

  const langLabel = (name: string): string | null => {
    const productLanguage = productLanguages[name] ?? { ru: true, en: true }
    if (!productLanguage.ru && !productLanguage.en) return 'скрыт'
    if (!productLanguage.ru) return 'только EN'
    if (!productLanguage.en) return 'только RU'
    return null
  }

  const card = (slide: Slide, index: number, collapsible: boolean) => (
    <SlideCard
      key={index}
      slide={slide}
      slideNumber={index + 1}
      newReqIds={newReqIds}
      changedReqIds={changedReqIds}
      expanded={collapsible ? !collapsedSlides.has(index) : true}
      onToggle={collapsible ? () => toggleSlide(index) : () => {}}
    />
  )

  return (
    <div className="grouped">
      {top.filter(isTitle).map((slide) => card(slide, slides.indexOf(slide), false))}
      {products.map((product) => (
        <div key={product.product} className="group">
          <div
            {...dropHandlers('', products.indexOf(product), products.map((item) => item.product))}
            className="group-header product-h"
          >
            <span className="badge">PRODUCT</span>
            <span className="group-title">{product.product}</span>
            {langLabel(product.product) && <span className="lang-badge">{langLabel(product.product)}</span>}
            <label
              className="inheritance-check"
              title="Во всех Stream продукта убирает фичи, уже показанные в предыдущих Tier, и добавляет заметку о наследовании"
            >
              <input
                type="checkbox"
                checked={!!productInheritanceFlags[product.product]}
                onChange={(event) => onToggleInheritance(product.product, event.target.checked)}
              />
              <span className="inheritance-check-text">
                Наследование
                <small>для всех Stream продукта</small>
              </span>
            </label>
          </div>
          {product.streams.map((stream) => (
            <div key={stream.stream} className="group">
              {stream.stream !== '-' && (
                <div
                  {...dropHandlers(
                    product.product,
                    product.streams.indexOf(stream),
                    product.streams.map((item) => item.stream),
                  )}
                  className="group-header stream-h"
                >
                  <span className="badge">STREAM</span>
                  <span className="group-title">{stream.stream}</span>
                </div>
              )}
              {stream.tiers.map((tier, tierIndex) => (
                <div key={tier.tier} className="group">
                  <div
                    {...dropHandlers(
                      `${product.product} > ${stream.stream}`,
                      tierIndex,
                      stream.tiers.map((item) => item.tier),
                    )}
                    className="group-header tier-h"
                  >
                    <span className="badge">TIER</span>
                    <span className="group-title">{tier.tier}</span>
                    {newTierPaths.has(`${product.product} > ${stream.stream} > ${tier.tier}`) && (
                      <span className="tree-badge">новое</span>
                    )}
                  </div>
                  {tier.slides.map((slide) => card(slide, slides.indexOf(slide), true))}
                </div>
              ))}
            </div>
          ))}
        </div>
      ))}
      {top.filter(isStatic).map((slide) => card(slide, slides.indexOf(slide), false))}
      {top.filter(isThankYou).map((slide) => card(slide, slides.indexOf(slide), false))}
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

function ProductLogosPanel({
  productNames,
  statuses,
  onUpload,
  onDelete,
}: {
  productNames: string[]
  statuses: Record<string, ProductLogoStatus>
  onUpload: (name: string, file: File) => void
  onDelete: (name: string) => void
}) {
  return (
    <div className="product-logos">
      {productNames.map((name) => {
        const st = statuses[name]
        return (
          <div key={name} className="product-logo-row">
            <span className="product-logo-name" title={name}>
              {name}
            </span>
            {st?.has_logo ? (
              <>
                <img className="product-logo-img" src={st.url ?? ''} alt={name} />
                <button className="logo-delete" onClick={() => onDelete(name)} title="Удалить лого">
                  ✕
                </button>
              </>
            ) : (
              <label className="logo-upload">
                Загрузить
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) onUpload(name, f)
                    e.target.value = ''
                  }}
                />
              </label>
            )}
          </div>
        )
      })}
    </div>
  )
}

function SlideCard({
  slide,
  slideNumber,
  newReqIds,
  changedReqIds,
  expanded,
  onToggle,
}: {
  slide: Slide
  slideNumber?: number
  newReqIds: Set<number>
  changedReqIds: Set<number>
  expanded: boolean
  onToggle: () => void
}) {
  if (isTitle(slide)) {
    return (
      <div className="card divider divider-title">
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
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
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
        <span className="divider-title">{slide.text}</span>
      </div>
    )
  }
  if (isStatic(slide)) {
    return (
      <div className="card divider divider-static">
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
        <span className="badge">STATIC</span>
        <span className="divider-title">{slide.name || '(без названия)'}</span>
      </div>
    )
  }
  if (isDivider(slide)) {
    return (
      <div className={'card divider divider-' + slide.divider_type}>
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
        <span className="badge">{slide.divider_type.toUpperCase()}</span>
        <span className="divider-title">{slide.title}</span>
      </div>
    )
  }
  return (
    <RoadmapCard
      slide={slide}
      slideNumber={slideNumber}
      newReqIds={newReqIds}
      changedReqIds={changedReqIds}
      expanded={expanded}
      onToggle={onToggle}
    />
  )
}

function RoadmapCard({
  slide,
  slideNumber,
  newReqIds,
  changedReqIds,
  expanded,
  onToggle,
}: {
  slide: RoadmapSlide
  slideNumber?: number
  newReqIds: Set<number>
  changedReqIds: Set<number>
  expanded: boolean
  onToggle: () => void
}) {
  return (
    <div className="card roadmap" onClick={onToggle}>
      <div className="roadmap-head">
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
        <span className="badge">{slide.continuation ? 'Roadmap (cont.)' : 'Roadmap'}</span>
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
