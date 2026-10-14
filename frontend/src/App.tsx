import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'
import type {
  Bullet,
  Column,
  DiffResponse,
  DividerSlide,
  LintIssue,
  PlanResponse,
  Profile,
  PublicFeaturesReport,
  QualityIssue,
  ReleaseInfo,
  ReleaseLog,
  RoadmapSlide,
  Slide,
  StaticSlide,
  TemplateInfo,
  ThankYouSlide,
  TitleSlide,
  Tree,
} from './types'
import {
  deleteProductSlideImage,
  deleteTemplate,
  deleteTierLogo,
  downloadPptx,
  downloadStaticSlidePptx,
  fetchDiff,
  fetchHealth,
  fetchPlan,
  fetchReleaseLog,
  getProductSlideImageStatuses,
  getProfile,
  getTierLogoStatuses,
  listTemplates,
  saveProfile,
  setActiveTemplate,
  uploadProductSlideImage,
  uploadPublicFeaturesReport,
  uploadStaticSlidePptx,
  uploadTemplate,
  uploadTierLogo,
  type ProductLogoStatus,
} from './api'
import {
  clearWorkspaceSession,
  readWorkspaceSession,
  saveWorkspaceSession,
  type WorkspaceSession,
} from './workspaceSession'

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
                  CrDate: '15.01.2025 21:00:00',
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
                      Kbr: 'Subject to Change',
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
                  CrDate: '15.04.2025 21:00:00',
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
  roadmap_title: 'Заголовок «Roadmap»',
  roadmap_cont_title: 'Заголовок продолжения',
}

type SaveState = 'idle' | 'saving' | 'saved' | 'error'
type AppTitleMode = 'auto' | 'on' | 'off'
type ExpansionLevel = 'products' | 'streams' | 'tiers' | 'features' | 'custom'
type BulkExpansionLevel = Exclude<ExpansionLevel, 'custom'>

function positionLabel(position: string): string {
  if (position === 'first') return 'Первый (заглавный) слайд'
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

const isRealNodeName = (name: string) => name.trim() !== '' && name.trim() !== '-'
const productNodeKey = (product: string) => JSON.stringify(['product', product])
const streamNodeKey = (product: string, stream: string) => JSON.stringify(['stream', product, stream])
const tierNodeKey = (product: string, stream: string, tier: string) =>
  JSON.stringify(['tier', product, stream, tier])

function usesTierLogoNames(productName: string): boolean {
  const normalized = productName.trim().replace(/\s+/g, ' ').toLocaleLowerCase('en')
  return ['next', 'kaspersky next', 'symphony'].includes(normalized) || normalized.startsWith('kaspersky symphony')
}

function slideBulletCount(slide: RoadmapSlide): number {
  return slide.columns.reduce(
    (total, column) => total + (column.grouped
      ? column.groups.reduce((groupTotal, group) => groupTotal + group.bullets.length, 0)
      : column.bullets.length),
    0,
  )
}

function tierBulletCount(tier: TierNode): number {
  return tier.slides.reduce((total, slide) => total + slideBulletCount(slide), 0)
}

function collectNodeKeys(products: ProductNode[]): Set<string> {
  const keys = new Set<string>()
  for (const product of products) {
    keys.add(productNodeKey(product.product))
    for (const stream of product.streams) {
      if (isRealNodeName(stream.stream)) keys.add(streamNodeKey(product.product, stream.stream))
      for (const tier of stream.tiers) {
        if (isRealNodeName(tier.tier)) keys.add(tierNodeKey(product.product, stream.stream, tier.tier))
      }
    }
  }
  return keys
}

function collapsedNodesForLevel(products: ProductNode[], level: BulkExpansionLevel): Set<string> {
  const collapsed = new Set<string>()
  if (level === 'features') return collapsed

  for (const product of products) {
    const productKey = productNodeKey(product.product)
    const realStreams = product.streams.filter((stream) => isRealNodeName(stream.stream))
    const realTiers = product.streams.flatMap((stream) =>
      stream.tiers.filter((tier) => isRealNodeName(tier.tier)),
    )

    if (level === 'products') {
      collapsed.add(productKey)
    } else if (level === 'streams') {
      // Если реальной иерархии нет, прямой Roadmap остаётся закрытым до уровня «Фичи».
      if (realStreams.length === 0 && realTiers.length === 0) collapsed.add(productKey)
    }

    for (const stream of realStreams) {
      const streamKey = streamNodeKey(product.product, stream.stream)
      const streamHasRealTiers = stream.tiers.some((tier) => isRealNodeName(tier.tier))
      if (level === 'streams' || (level === 'tiers' && !streamHasRealTiers)) collapsed.add(streamKey)
    }

    for (const stream of product.streams) {
      for (const tier of stream.tiers) {
        if (isRealNodeName(tier.tier)) {
          collapsed.add(tierNodeKey(product.product, stream.stream, tier.tier))
        }
      }
    }
  }
  return collapsed
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
  // Product без единой фичи после фильтрации или скрытия языка)
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

interface DragBinding {
  handleProps: {
    draggable: boolean
    tabIndex: number
    'aria-label': string
    onClick: (e: ReactMouseEvent) => void
    onDragStart: (e: DragEvent) => void
    onDragEnd: (e: DragEvent) => void
    onKeyDown: (e: ReactKeyboardEvent) => void
  }
  targetProps: {
    onDragOver: (e: DragEvent) => void
    onDragLeave: (e: DragEvent) => void
    onDrop: (e: DragEvent) => void
  }
}

type DropHandlerFactory = (
  parentPath: string,
  index: number,
  siblings: string[],
  siblingKeys: string[],
) => DragBinding

export default function App() {
  const [jsonText, setJsonText] = useState('')
  const [jsonData, setJsonData] = useState<unknown>(null)
  const [language, setLanguage] = useState<'ru' | 'en'>('ru')
  const [apptitleMode, setApptitleMode] = useState<AppTitleMode>('auto')
  const [result, setResult] = useState<PlanResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [appVersion, setAppVersion] = useState('')
  const [releaseLog, setReleaseLog] = useState<ReleaseLog | null>(null)
  const [releaseLogOpen, setReleaseLogOpen] = useState(false)
  const [releaseLogLoading, setReleaseLogLoading] = useState(false)
  const [releaseLogError, setReleaseLogError] = useState<string | null>(null)
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
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [rightWidth, setRightWidth] = useState(320)
  const [collapsedNodes, setCollapsedNodes] = useState<Set<string>>(new Set())
  const [expansionLevel, setExpansionLevel] = useState<ExpansionLevel>('features')
  const [lastBulkExpansionLevel, setLastBulkExpansionLevel] = useState<BulkExpansionLevel>('features')
  const [workspaceSessionReady, setWorkspaceSessionReady] = useState(false)
  const [recentlyReorderedNodes, setRecentlyReorderedNodes] = useState<Set<string>>(new Set())
  const [workspaceView, setWorkspaceView] = useState<'preview' | 'quality' | 'reports'>('preview')
  const [publicFeaturesReport, setPublicFeaturesReport] = useState<PublicFeaturesReport | null>(null)
  const [publicFeaturesFile, setPublicFeaturesFile] = useState<File | null>(null)
  const [publicFeaturesLoading, setPublicFeaturesLoading] = useState(false)
  const [publicFeaturesError, setPublicFeaturesError] = useState<string | null>(null)
  const publicFeaturesRequestRef = useRef(0)
  const [staticModal, setStaticModal] = useState({ open: false, editIndex: null as number | null, name: '', position: 'end', pptx: '', prompt: '' })
  const [productSlideStatus, setProductSlideStatus] = useState<Record<string, ProductLogoStatus>>({})
  const [productSlideRefresh, setProductSlideRefresh] = useState(0)
  const [tierLogoStatus, setTierLogoStatus] = useState<Record<string, ProductLogoStatus>>({})
  const [tierLogoRefresh, setTierLogoRefresh] = useState(0)
  const saveTimerRef = useRef<number | null>(null)
  const pendingProfileRef = useRef<Profile | null>(null)
  const knownNodeKeysRef = useRef<Set<string> | null>(null)
  const pendingReorderFlashRef = useRef<string[] | null>(null)
  const reorderFlashTimerRef = useRef<number | null>(null)
  const reorderFlashFrameRef = useRef<number | null>(null)

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
  const tierLogoNames = useMemo(() => [...new Set(
    (result?.tree?.products ?? []).flatMap((product) => {
      const useTiers = usesTierLogoNames(product.name)
      return useTiers
        ? product.streams.flatMap((stream) => stream.tiers.map((tier) => tier.name))
        : [product.name]
    }),
  )], [result])

  useEffect(() => {
    if (!productNames.length) return
    let alive = true
    getProductSlideImageStatuses(productNames)
      .then((statuses) => {
        if (alive) setProductSlideStatus(statuses)
      })
      .catch(() => {})
    return () => { alive = false }
  }, [productNames, productSlideRefresh])

  // Статус логотипов тиров.
  useEffect(() => {
    if (!tierLogoNames.length) return
    let alive = true
    getTierLogoStatuses(tierLogoNames)
      .then((statuses) => {
        if (alive) setTierLogoStatus(statuses)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [tierLogoNames, tierLogoRefresh])

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

  function openReleaseLog() {
    setReleaseLogOpen(true)
    if (releaseLog || releaseLogLoading) return
    setReleaseLogLoading(true)
    setReleaseLogError(null)
    fetchReleaseLog()
      .then(setReleaseLog)
      .catch((error) => setReleaseLogError(String(error)))
      .finally(() => setReleaseLogLoading(false))
  }

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
    if (!result?.plan) return
    const { products } = groupSlides(result.plan.slides, result.tree)
    const validKeys = collectNodeKeys(products)
    if (expansionLevel !== 'custom') {
      setCollapsedNodes(collapsedNodesForLevel(products, expansionLevel))
      knownNodeKeysRef.current = validKeys
      return
    }
    setCollapsedNodes((previous) => {
      const next = new Set([...previous].filter((key) => validKeys.has(key)))
      const knownKeys = knownNodeKeysRef.current
      if (knownKeys) {
        const defaultCollapsed = collapsedNodesForLevel(products, lastBulkExpansionLevel)
        for (const key of validKeys) {
          if (!knownKeys.has(key) && defaultCollapsed.has(key)) next.add(key)
        }
      }
      return next
    })
    knownNodeKeysRef.current = validKeys
  }, [result, expansionLevel, lastBulkExpansionLevel])

  useEffect(() => {
    if (!result?.plan || !pendingReorderFlashRef.current) return
    const keys = pendingReorderFlashRef.current
    pendingReorderFlashRef.current = null
    if (reorderFlashTimerRef.current !== null) window.clearTimeout(reorderFlashTimerRef.current)
    if (reorderFlashFrameRef.current !== null) window.cancelAnimationFrame(reorderFlashFrameRef.current)
    setRecentlyReorderedNodes(new Set())
    reorderFlashFrameRef.current = window.requestAnimationFrame(() => {
      setRecentlyReorderedNodes(new Set(keys))
      reorderFlashTimerRef.current = window.setTimeout(() => {
        setRecentlyReorderedNodes(new Set())
        reorderFlashTimerRef.current = null
      }, 1400)
      reorderFlashFrameRef.current = null
    })
  }, [result])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  useEffect(() => {
    let active = true
    readWorkspaceSession()
      .then((session) => {
        if (!active || !session) return
        setJsonText(session.jsonText)
        setJsonData(session.jsonData)
        setLanguage(session.language)
        setApptitleMode(session.apptitleMode)
        setLeftCollapsed(session.leftCollapsed)
        setRightCollapsed(session.rightCollapsed)
        setRightWidth(session.rightWidth)
        setCollapsedNodes(new Set(session.collapsedNodes))
        setExpansionLevel(session.expansionLevel)
        setLastBulkExpansionLevel(session.lastBulkExpansionLevel)
      })
      .catch(() => {
        if (active) setError('Не удалось восстановить рабочую сессию из хранилища браузера.')
      })
      .finally(() => {
        if (active) setWorkspaceSessionReady(true)
      })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!workspaceSessionReady) return
    const session: WorkspaceSession = {
      version: 2,
      jsonData,
      jsonText,
      language,
      apptitleMode,
      leftCollapsed,
      rightCollapsed,
      rightWidth,
      collapsedNodes: [...collapsedNodes],
      expansionLevel,
      lastBulkExpansionLevel,
    }
    saveWorkspaceSession(session).catch(() => {
      setError('Не удалось сохранить рабочую сессию в хранилище браузера.')
    })
  }, [workspaceSessionReady, jsonData, jsonText, language, apptitleMode, leftCollapsed, rightCollapsed, rightWidth, collapsedNodes, expansionLevel, lastBulkExpansionLevel])

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
      if (reorderFlashTimerRef.current !== null) window.clearTimeout(reorderFlashTimerRef.current)
      if (reorderFlashFrameRef.current !== null) window.cancelAnimationFrame(reorderFlashFrameRef.current)
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
    if (publicFeaturesFile) void refreshPublicFeatures(data, publicFeaturesFile)
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
        if (publicFeaturesFile) void refreshPublicFeatures(data, publicFeaturesFile)
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
    clearWorkspaceSession().catch(() => {
      setError('Не удалось очистить рабочую сессию в хранилище браузера.')
    })
    setJsonText('')
    setJsonData(null)
    setResult(null)
    setDiff(null)
    publicFeaturesRequestRef.current += 1
    setPublicFeaturesLoading(false)
    setWorkspaceView('preview')
    setError(null)
    setNotice(null)
    setCollapsedNodes(new Set())
    setExpansionLevel('features')
    setLastBulkExpansionLevel('features')
    knownNodeKeysRef.current = null
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

  async function refreshPublicFeatures(data: unknown, file: File, rememberFile = false) {
    const requestId = publicFeaturesRequestRef.current + 1
    publicFeaturesRequestRef.current = requestId
    setPublicFeaturesLoading(true)
    setPublicFeaturesError(null)
    try {
      const uploadedReport = await uploadPublicFeaturesReport(data, file)
      if (publicFeaturesRequestRef.current === requestId) {
        setPublicFeaturesReport(uploadedReport)
        if (rememberFile) setPublicFeaturesFile(file)
      }
    } catch (uploadError) {
      const message = uploadError instanceof Error ? uploadError.message : String(uploadError)
      if (publicFeaturesRequestRef.current === requestId) setPublicFeaturesError(message)
    } finally {
      if (publicFeaturesRequestRef.current === requestId) setPublicFeaturesLoading(false)
    }
  }

  async function handlePublicFeaturesUpload(file: File) {
    if (!jsonData) return
    await refreshPublicFeatures(jsonData, file, true)
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

  function handleReorder(parentPath: string, names: string[], highlightKeys: string[]) {
    if (!profile) return
    pendingReorderFlashRef.current = highlightKeys
    persist({
      ...profile,
      ordering: { ...profile.ordering, order: { ...profile.ordering.order, [parentPath]: names } },
    })
  }

  function handleToggleProductSlide(productName: string, generate: boolean, selectedLanguage: 'ru' | 'en') {
    if (!profile) return
    const legacyFlags = profile.ordering.product_slide_hidden_flags ?? {}
    const flagsByLanguage = profile.ordering.product_slide_hidden_flags_by_language ?? {
      ru: { ...legacyFlags },
      en: { ...legacyFlags },
    }
    persist({
      ...profile,
      ordering: {
        ...profile.ordering,
        product_slide_hidden_flags_by_language: {
          ...flagsByLanguage,
          [selectedLanguage]: {
            ...flagsByLanguage[selectedLanguage],
            [productName]: !generate,
          },
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

  function toggleNode(key: string) {
    setExpansionLevel('custom')
    setCollapsedNodes((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function applyExpansionLevel(level: BulkExpansionLevel) {
    setExpansionLevel(level)
    setLastBulkExpansionLevel(level)
    if (!result?.plan) return
    const { products } = groupSlides(result.plan.slides, result.tree)
    setCollapsedNodes(collapsedNodesForLevel(products, level))
  }

  function openStaticSlideModal(position = 'end', editIndex: number | null = null) {
    const existing = editIndex === null ? null : profile?.static_slides?.[editIndex]
    setStaticModal({
      open: true,
      editIndex,
      name: existing?.name ?? '',
      position: existing?.position ?? position,
      pptx: existing?.pptx ?? '',
      prompt: existing?.prompt ?? '',
    })
  }

  function handleDeleteStaticSlide(index: number) {
    if (!profile) return
    handleStaticSlides((profile.static_slides ?? []).filter((_, k) => k !== index))
  }

  function handleStaticSlidePrompt(index: number, prompt: string) {
    if (!profile) return
    handleStaticSlides((profile.static_slides ?? []).map((slide, slideIndex) =>
      slideIndex === index ? { ...slide, prompt } : slide,
    ))
  }

  function handleDownloadStaticSlide(filename: string) {
    setError(null)
    downloadStaticSlidePptx(filename)
      .catch(() => setError('Не удалось скачать статичный слайд.'))
  }

  function closeStaticSlideModal() {
    setStaticModal((m) => ({ ...m, open: false }))
  }

  function submitStaticSlide() {
    if (!profile) return
    const nextSlide = {
      name: staticModal.name,
      position: staticModal.position,
      pptx: staticModal.pptx,
      prompt: staticModal.prompt,
      language,
    }
    const slides = [...(profile.static_slides ?? [])]
    if (staticModal.editIndex === null) slides.push(nextSlide)
    else slides[staticModal.editIndex] = { ...slides[staticModal.editIndex], ...nextSlide }
    handleStaticSlides(slides)
    closeStaticSlideModal()
  }

  function handleDeckMeta(field: 'title' | 'year' | 'version', value: string) {
    if (!profile) return
    persist({ ...profile, deck_meta: { ...profile.deck_meta, [field]: value } })
  }

  function handleThankYouText(lang: 'ru' | 'en', value: string) {
    if (!profile) return
    persist({
      ...profile,
      deck_meta: {
        ...profile.deck_meta,
        thank_you_text: { ...profile.deck_meta.thank_you_text, [lang]: value },
      },
    })
  }

  function handleDeckSlideToggle(
    field: 'include_title_slide' | 'include_thank_you_slide',
    value: boolean,
  ) {
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
    persist({ ...profile, labels: { ...profile.labels, [original]: custom } })
  }

  function handleRemoveLabel(original: string) {
    if (!profile) return
    const labels = { ...profile.labels }
    delete labels[original]
    persist({ ...profile, labels })
  }

  function handlePriority(names: string[]) {
    if (!profile) return
    persist({ ...profile, ordering: { ...profile.ordering, apptitle_priority: names } })
  }

  function handleStaticSlides(slides: {
    name: string
    position: string
    pptx: string
    prompt: string
    language: 'ru' | 'en'
  }[]) {
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

  function handleTierName(name: string, lang: 'ru' | 'en', value: string) {
    if (!profile) return
    const current = profile.tier_names?.[name] ?? { ru: '', en: '' }
    persist({
      ...profile,
      tier_names: { ...profile.tier_names, [name]: { ...current, [lang]: value } },
    })
  }

  function handleUploadProductSlideImage(name: string, file: File) {
    uploadProductSlideImage(name, file)
      .then(() => setProductSlideRefresh((n) => n + 1))
      .catch(() => setError('Не удалось загрузить PNG-фон продуктового слайда.'))
  }

  function handleDeleteProductSlideImage(name: string) {
    deleteProductSlideImage(name)
      .then(() => setProductSlideRefresh((n) => n + 1))
      .catch(() => setError('Не удалось удалить фон продуктового слайда.'))
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

  const dropHandlers: DropHandlerFactory = (parentPath, index, siblings, siblingKeys) => ({
    handleProps: {
      draggable: true,
      tabIndex: 0,
      'aria-label': `${siblings[index]}. Перетаскивание внутри текущей группы. Alt и стрелки меняют порядок.`,
      onClick: (e) => e.stopPropagation(),
      onDragStart: (e) => {
        e.stopPropagation()
        dragRef.current = { parentPath, index }
        e.dataTransfer.effectAllowed = 'move'
        e.dataTransfer.setData('text/plain', String(index))
        e.currentTarget.closest('.group-header')?.classList.add('dragging')
      },
      onDragEnd: (e) => {
        e.stopPropagation()
        e.currentTarget.closest('.group-header')?.classList.remove('dragging')
        dragRef.current = null
      },
      onKeyDown: (e) => {
        if (!e.altKey || (e.key !== 'ArrowUp' && e.key !== 'ArrowDown')) return
        e.preventDefault()
        e.stopPropagation()
        const target = e.key === 'ArrowUp' ? index - 1 : index + 1
        if (target >= 0 && target < siblings.length) {
          handleReorder(
            parentPath,
            moveItem(siblings, index, target),
            [siblingKeys[index], siblingKeys[target]],
          )
        }
      },
    },
    targetProps: {
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
        handleReorder(
          parentPath,
          moveItem(siblings, d.index, index),
          [siblingKeys[d.index], siblingKeys[index]],
        )
        dragRef.current = null
      },
    },
  })

  const planErrors = result?.errors ?? []
  const planWarnings = result?.warnings ?? []
  const planConflicts = result?.plan?.conflicts ?? []
  const lintIssues = result?.lint_issues ?? []
  const dataQualityIssues = result?.quality_issues ?? []
  const qualityCount = planErrors.length + planWarnings.length + planConflicts.length + lintIssues.length + dataQualityIssues.length
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
          {appVersion && (
            <button
              type="button"
              className="app-version"
              title="Открыть журнал релиза"
              onClick={openReleaseLog}
            >
              v{appVersion}
            </button>
          )}
        </div>
        <div className="header-actions">
          {Boolean(jsonData) && (
            <button
              type="button"
              className={'status-pill ' + (planErrors.length ? 'error' : qualityCount ? 'warning' : 'success')}
              onClick={() => qualityCount > 0 && setWorkspaceView('quality')}
              disabled={qualityCount === 0 || loading}
              title={qualityCount > 0 ? 'Открыть контроль качества данных' : 'Замечаний нет'}
            >
              {loading ? 'Проверяем…' : planErrors.length ? 'Есть ошибки' : qualityCount ? `${qualityCount} замеч.` : 'Готово'}
            </button>
          )}
          {Boolean(jsonData) && (
            <button
              type="button"
              className={'reports-button' + (workspaceView === 'reports' ? ' active' : '')}
              onClick={() => setWorkspaceView('reports')}
              disabled={loading}
            >
              Отчёты
            </button>
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
        ) : workspaceView === 'quality' ? (
          <QualityDashboard
            issues={dataQualityIssues}
            warnings={planWarnings}
            conflicts={planConflicts}
            lintIssues={lintIssues}
            onBack={() => setWorkspaceView('preview')}
          />
        ) : workspaceView === 'reports' ? (
          <ReportsDashboard
            report={result?.report ?? null}
            publicFeatures={publicFeaturesReport}
            publicFeaturesLoading={publicFeaturesLoading}
            publicFeaturesError={publicFeaturesError}
            onUpload={handlePublicFeaturesUpload}
            onBack={() => setWorkspaceView('preview')}
          />
        ) : (
          <>
            {loading && <p>Загрузка…</p>}
            {notice && <div className="message success-message" role="status"><strong>Готово</strong><span>{notice}</span></div>}
            {diff && diff.diff && (
              <DiffSummary diff={diff} />
            )}

            {result && result.plan && (
              <>
                <div className="slides-toolbar">
                  <div className="expansion-levels" role="group" aria-label="Уровень раскрытия структуры">
                    <span>Показать:</span>
                    {([
                      ['products', 'Продукты', 'Оставить только плашки продуктов'],
                      ['streams', 'Стримы', 'Раскрыть продукты до ближайшего уровня Stream'],
                      ['tiers', 'Тиры', 'Раскрыть структуру до Tier, не показывая фичи'],
                      ['features', 'Фичи', 'Полностью раскрыть все Roadmap'],
                    ] as const).map(([level, label, title]) => (
                      <button
                        key={level}
                        className={expansionLevel === level ? 'active' : ''}
                        onClick={() => applyExpansionLevel(level)}
                        aria-pressed={expansionLevel === level}
                        title={title}
                      >
                        {label}
                      </button>
                    ))}
                    {expansionLevel === 'custom' && <span className="custom-level">Выборочно</span>}
                  </div>
                </div>
                <div className="slides">
                  <GroupedSlides
                    slides={result.plan.slides}
                    tree={result.tree}
                    dropHandlers={dropHandlers}
                    newReqIds={newReqIds}
                    changedReqIds={changedReqIds}
                    collapsedNodes={collapsedNodes}
                    toggleNode={toggleNode}
                    recentlyReorderedNodes={recentlyReorderedNodes}
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
              setRightWidth(Math.max(240, startWidth + (startX - ev.clientX)))
            const onUp = () => {
              window.removeEventListener('mousemove', onMove)
              window.removeEventListener('mouseup', onUp)
            }
            window.addEventListener('mousemove', onMove)
            window.addEventListener('mouseup', onUp)
          }}
        />
        <details className="section">
          <summary>Библиотека шаблонов</summary>
          <TemplatesPanel />
        </details>

        {profile && (
          <details className="section">
            <summary>Статичные слайды · {language.toUpperCase()}</summary>
            <button className="section-primary-action" onClick={() => openStaticSlideModal()}>
              ＋ Добавить статичный слайд
            </button>
            <StaticSlidesList
              slides={profile.static_slides ?? []}
              language={language}
              onPromptChange={handleStaticSlidePrompt}
              onEdit={(index) => openStaticSlideModal('end', index)}
              onDownload={handleDownloadStaticSlide}
              onDelete={handleDeleteStaticSlide}
            />
          </details>
        )}

        {profile && productNames.length > 0 && (
          <details className="section">
            <summary>Слайды продуктов</summary>
            <ProductSlideVisibilityPanel
              productNames={productNames}
              hiddenFlags={
                profile.ordering.product_slide_hidden_flags_by_language?.[language] ??
                profile.ordering.product_slide_hidden_flags ?? {}
              }
              onChange={(name, generate) => handleToggleProductSlide(name, generate, language)}
            />
          </details>
        )}

        {profile && productNames.length > 0 && (
          <details className="section">
            <summary>Языки продуктов</summary>
            <ProductLanguagesPanel
              productNames={productNames}
              tierNames={tierNames}
              languages={profile.product_languages ?? {}}
              localizedTierNames={profile.tier_names ?? {}}
              onChange={handleProductLanguage}
              onTierNameChange={handleTierName}
            />
          </details>
        )}

        {profile && productNames.length > 0 && (
          <details className="section">
            <summary>Фоны продуктовых слайдов</summary>
            <div className="product-slide-help">
              PNG-фон подставляется на страницу-заглушку соответствующего продукта.
            </div>
            <ProductLogosPanel
              productNames={productNames}
              statuses={productSlideStatus}
              onUpload={handleUploadProductSlideImage}
              onDelete={handleDeleteProductSlideImage}
              accept="image/png,.png"
              deleteTitle="Удалить фон"
            />
          </details>
        )}

        {profile && tierLogoNames.length > 0 && (
          <details className="section">
            <summary>Логотипы тиров</summary>
            <ProductLogosPanel
              productNames={tierLogoNames}
              statuses={tierLogoStatus}
              onUpload={handleUploadTierLogo}
              onDelete={handleDeleteTierLogo}
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

        {profile && (
          <details className="section">
            <summary>App group mapping</summary>
            <SynonymsPanel
              labels={profile.labels}
              appTitles={appTitles}
              onChange={handleLabel}
              onRemove={handleRemoveLabel}
            />
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
        </div>

        {profile && (
          <details className="section">
            <summary>{'\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0430 \u0442\u0438\u0442\u0443\u043b\u044c\u043d\u043e\u0433\u043e \u0438 \u0444\u0438\u043d\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0441\u043b\u0430\u0439\u0434\u043e\u0432'}</summary>
            <div className="deck-meta">
            <span className="deck-meta-title">Титульный слайд</span>
            <label className="deck-slide-toggle">
              <input
                type="checkbox"
                checked={profile?.deck_meta?.include_title_slide !== false}
                onChange={(e) => handleDeckSlideToggle('include_title_slide', e.target.checked)}
              />
              Генерировать первый слайд
            </label>
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
            <label className="deck-slide-toggle">
              <input
                type="checkbox"
                checked={profile?.deck_meta?.include_thank_you_slide !== false}
                onChange={(e) => handleDeckSlideToggle('include_thank_you_slide', e.target.checked)}
              />
              Генерировать финальный слайд
            </label>
            <div className="deck-meta-row">
              <input
                type="text"
                aria-label="Final slide text, RU"
                placeholder="RU"
                value={profile.deck_meta.thank_you_text.ru}
                onChange={(e) => handleThankYouText('ru', e.target.value)}
              />
              <input
                type="text"
                aria-label="Final slide text, EN"
                placeholder="EN"
                value={profile.deck_meta.thank_you_text.en}
                onChange={(e) => handleThankYouText('en', e.target.value)}
              />
            </div>
            </div>
          </details>
        )}
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
      <ReleaseLogModal
        open={releaseLogOpen}
        version={appVersion}
        releaseLog={releaseLog}
        loading={releaseLogLoading}
        error={releaseLogError}
        onClose={() => setReleaseLogOpen(false)}
      />
    </div>
  )
}

const RELEASE_PROBLEM_LABELS: Record<string, string> = {
  missing_crdate: 'CrDate не заполнена',
  invalid_crdate: 'CrDate не распознана',
  invalid_trdate: 'TrDate не распознана',
  missing_app_title: 'AppTitle не заполнен',
  empty_requirements: 'Нет Requirements',
}
const REPORT_YEARS = ['2026', '2027'] as const

function ReportsDashboard({
  report,
  publicFeatures,
  publicFeaturesLoading,
  publicFeaturesError,
  onUpload,
  onBack,
}: {
  report: PlanResponse['report'] | null
  publicFeatures: PublicFeaturesReport | null
  publicFeaturesLoading: boolean
  publicFeaturesError: string | null
  onUpload: (file: File) => void
  onBack: () => void
}) {
  const [selectedYear, setSelectedYear] = useState<(typeof REPORT_YEARS)[number]>('2026')
  const maxUnmapped = Math.max(1, ...(publicFeatures?.products.map((product) => product.unmapped) ?? []))
  const yearReport = report?.years[selectedYear] ?? null
  const completeProducts = publicFeatures?.complete_products_by_year[selectedYear] ?? []

  return (
    <section className="reports-workspace">
      <div className="reports-workspace-header">
        <div>
          <span className="eyebrow">Текущий JSON</span>
          <h2>Отчёты</h2>
          <p>Ключевые показатели состава JSON и качества релизов.</p>
        </div>
        <button type="button" onClick={onBack}>← К презентации</button>
      </div>

      <section className="public-features-report">
        <div className="public-features-heading">
          <div>
            <h3>Публичные фичи без маппинга</h3>
            <p>CSV сопоставляется с текущим JSON по ReqId. Файл не сохраняется.</p>
          </div>
          <label className={'csv-upload-button' + (publicFeaturesLoading ? ' disabled' : '')}>
            {publicFeaturesLoading ? 'Проверяем…' : publicFeatures ? 'Заменить CSV' : 'Загрузить CSV'}
            <input
              type="file"
              accept=".csv,text/csv,text/tab-separated-values"
              disabled={publicFeaturesLoading}
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) onUpload(file)
                event.target.value = ''
              }}
            />
          </label>
        </div>
        <p className="public-features-hint">
          CSV с разделителем TAB (также распознаются «;» и «,»). Обязательные колонки: <code>ReqId</code>, <code>IsPublished</code> и <code>ApplicableForProducts</code>. Для группировки используются <code>Application</code> и <code>Requirement</code>.
        </p>

        {publicFeaturesError && <div className="message error-message" role="alert">{publicFeaturesError}</div>}

        {publicFeatures && (
          <>
            <div className="public-features-summary">
              <div><span>Публичных фичей</span><strong>{publicFeatures.public_features}</strong></div>
              <div><span>Есть в JSON</span><strong>{publicFeatures.mapped_public_features}</strong></div>
              <div className={publicFeatures.unmapped_public_features ? 'warning' : 'success'}>
                <span>Не замаплено</span><strong>{publicFeatures.unmapped_public_features}</strong>
              </div>
            </div>
            <div className="public-features-file">
              {publicFeatures.filename} · найдено в JSON {publicFeatures.mapped_percent}%
              {publicFeatures.invalid_req_id_rows > 0 && ` · пропущено строк без ReqId: ${publicFeatures.invalid_req_id_rows}`}
            </div>

            {publicFeatures.products.length > 0 ? (
              <div className="public-features-chart" aria-label="Незамапленные публичные фичи по продуктам">
                {publicFeatures.products.map((product) => (
                  <details className="public-feature-product" key={product.product}>
                    <summary>
                      <span className="public-feature-product-name">{product.product}</span>
                      <span className="public-feature-bar" aria-hidden="true">
                        <span style={{ width: `${product.unmapped * 100 / maxUnmapped}%` }} />
                      </span>
                      <strong>{product.unmapped}</strong>
                    </summary>
                    <div className="public-feature-requirements">
                      {product.requirements.map((requirement) => (
                        <div key={requirement.req_id}>
                          <code>{requirement.req_id}</code>
                          <span>{requirement.title || 'Без названия'}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <div className="public-features-complete">Все публичные фичи из CSV найдены в текущем JSON.</div>
            )}
          </>
        )}
      </section>

      <div className="reports-year-tabs" role="tablist" aria-label="Год отчёта">
        {REPORT_YEARS.map((year) => (
          <button
            key={year}
            type="button"
            role="tab"
            aria-selected={selectedYear === year}
            className={selectedYear === year ? 'active' : ''}
            onClick={() => setSelectedYear(year)}
          >
            {year}
          </button>
        ))}
      </div>

      <section className="report-year-panel" role="tabpanel" aria-label={`Отчёт за ${selectedYear} год`}>
        {yearReport ? (
          <>
            <div className="reports-summary-cards">
              <div>
                <span>Уникальные Requirements</span>
                <strong>{yearReport.requirements.unique}</strong>
                <small>
                  {yearReport.requirements.occurrences} вхождений = {yearReport.requirements.unique} первых +{' '}
                  {yearReport.requirements.duplicate_occurrences} повторных; {yearReport.requirements.reused} ReqId повторяются
                </small>
              </div>
              <div className={yearReport.releases.with_problems ? 'warning' : ''}>
                <span>Релизы с проблемами</span>
                <strong>{yearReport.releases.with_problems} из {yearReport.releases.total}</strong>
                <small>Год определяется только по TrDate</small>
              </div>
              <div className={yearReport.releases.missing_crdate ? 'warning' : ''}>
                <span>Без CrDate</span>
                <strong>{yearReport.releases.missing_crdate}</strong>
                <small>Проверка заполненности и формата CrDate</small>
              </div>
            </div>

            {yearReport.release_problems.length > 0 ? (
              <details className="report-release-details">
                <summary>Проблемные релизы ({yearReport.release_problems.length})</summary>
                <div className="quality-table-wrap">
                  <table className="quality-table">
                    <thead><tr><th>Релиз</th><th>Проблемы</th><th>TrDate</th><th>CrDate</th></tr></thead>
                    <tbody>
                      {yearReport.release_problems.map((release, index) => {
                        const title = release.title || `Release ${release.release_id ?? '—'}`
                        return (
                          <tr key={`${release.release_id ?? 'unknown'}-${index}`}>
                            <td>
                              {release.tfs_url ? (
                                <a href={release.tfs_url} target="_blank" rel="noreferrer noopener"><strong>{title}</strong></a>
                              ) : <strong>{title}</strong>}
                              <small>{release.product} · {release.stream} · {release.tier}</small>
                            </td>
                            <td>{release.codes.map((code) => RELEASE_PROBLEM_LABELS[code] ?? code).join(', ')}</td>
                            <td>{release.trdate || '—'}</td>
                            <td>{release.crdate || '—'}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </details>
            ) : (
              <p className="quality-empty">Проблемных релизов за {selectedYear} год нет.</p>
            )}

            <section className="complete-products-report">
              <h3>Заполненные продукты</h3>
              {!publicFeatures ? (
                <p>Загрузите CSV выше, чтобы проверить ApplicableForProducts для всех Requirements.</p>
              ) : completeProducts.length > 0 ? (
                <ul>{completeProducts.map((product) => <li key={product}>{product}</li>)}</ul>
              ) : (
                <p>За {selectedYear} год нет продуктов, полностью заполненных по CrDate и ApplicableForProducts.</p>
              )}
            </section>
          </>
        ) : (
          <p className="quality-empty">Отчёт рассчитывается…</p>
        )}
      </section>
    </section>
  )
}

function DiffSummary({ diff }: { diff: DiffResponse }) {
  const groups = [
    ['Новые требования', diff.details?.new_requirements ?? []],
    ['Изменённые требования', diff.details?.changed_requirements ?? []],
    ['Удалённые требования', diff.details?.removed_requirements ?? []],
    ['Новые релизы', diff.details?.new_releases ?? []],
    ['Изменённые релизы', diff.details?.changed_releases ?? []],
    ['Удалённые релизы', diff.details?.removed_releases ?? []],
  ] as const
  const fieldLabel: Record<string, string> = {
    text: 'название',
    kbr: 'Kbr',
    title: 'релиз',
    quarter: 'квартал',
  }
  const value = (item: unknown) => item === null || item === undefined || item === '' ? '—' : String(item)

  return (
    <details className="diff-summary" open>
      <summary>
        <b>Изменения относительно прошлой загрузки</b>
        <span>
          +{diff.diff.new_requirement_ids?.length ?? 0} ·
          {' '}~{diff.diff.changed_requirement_ids?.length ?? 0} ·
          {' '}−{diff.diff.removed_requirement_ids?.length ?? 0}
        </span>
      </summary>
      <div className="diff-details">
        {diff.new_tier_paths.length > 0 && (
          <div><b>Новые тиры:</b> {diff.new_tier_paths.join(', ')}</div>
        )}
        {diff.removed_tier_paths.length > 0 && (
          <div><b>Удалённые тиры:</b> {diff.removed_tier_paths.join(', ')}</div>
        )}
        {groups.filter(([, items]) => items.length > 0).map(([label, items]) => (
          <section key={label} className="diff-group">
            <b>{label}</b>
            {items.map((item) => (
              <div key={`${label}:${item.id}`} className="diff-item">
                <span>{item.text || item.title || `ID ${item.id}`}</span>
                <small>{item.path}</small>
                {item.changes && Object.entries(item.changes).map(([field, change]) => (
                  <small key={field}>
                    {fieldLabel[field] ?? field}: {value(change.before)} → {value(change.after)}
                  </small>
                ))}
              </div>
            ))}
          </section>
        ))}
      </div>
    </details>
  )
}

function QualityDashboard({
  issues,
  warnings,
  conflicts,
  lintIssues,
  onBack,
}: {
  issues: QualityIssue[]
  warnings: string[]
  conflicts: string[]
  lintIssues: LintIssue[]
  onBack: () => void
}) {
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLocaleLowerCase('ru')
  const filtered = normalizedQuery
    ? issues.filter((issue) => [issue.rpp_title, issue.trdate, issue.quarter, issue.product, issue.stream, issue.tier]
        .some((value) => value.toLocaleLowerCase('ru').includes(normalizedQuery)))
    : issues

  return (
    <section className="quality-workspace">
      <div className="quality-workspace-header">
        <div>
          <span className="eyebrow">Контроль качества</span>
          <h2>Замечания к данным</h2>
          <p>Исправьте источник JSON и загрузите выгрузку повторно. Роадмап пока строится с указанным fallback.</p>
        </div>
        <button type="button" onClick={onBack}>← К презентации</button>
      </div>

      <div className="quality-summary-cards">
        <div><strong>{issues.length}</strong><span>структурированных замечаний</span></div>
        <div><strong>{warnings.length + conflicts.length}</strong><span>системных предупреждений</span></div>
        <div><strong>{lintIssues.length}</strong><span>ошибок текстов</span></div>
      </div>

      {issues.length > 0 && (
        <>
          <div className="quality-table-toolbar">
            <h3>Даты релизов</h3>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск по RPP title, дате, кварталу…"
            />
          </div>
          <div className="quality-table-wrap">
            <table className="quality-table">
              <thead><tr><th>Проверка</th><th>RPP title</th><th>TrDate</th><th>Квартал</th></tr></thead>
              <tbody>
                {filtered.map((issue) => (
                  <tr key={`${issue.code}-${issue.release_id}-${issue.product}-${issue.tier}`}>
                    <td><span className={`quality-severity ${issue.severity}`}>{issue.message}</span></td>
                    <td><strong>{issue.rpp_title || `Release ${issue.release_id}`}</strong><small>{issue.product} · {issue.stream} · {issue.tier}</small></td>
                    <td>{issue.trdate}</td>
                    <td>{issue.quarter}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && <p className="quality-empty">По этому запросу замечаний нет.</p>}
          </div>
        </>
      )}

      {(warnings.length > 0 || conflicts.length > 0 || lintIssues.length > 0) && (
        <details className="quality-secondary">
          <summary>Другие замечания ({warnings.length + conflicts.length + lintIssues.length})</summary>
          <ul>
            {warnings.map((warning, index) => <li key={`warning-${index}`}>{warning}</li>)}
            {conflicts.map((conflict, index) => <li key={`conflict-${index}`}>{conflict}</li>)}
            {lintIssues.map((issue, index) => <li key={`lint-${index}`}>{issue.message}: «{issue.text}»</li>)}
          </ul>
        </details>
      )}
    </section>
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
      {Object.entries(strings).filter(([key]) => key !== 'thank_you').map(([key, langs]) => (
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
  onRemove,
}: {
  labels: Record<string, string>
  appTitles: string[]
  onChange: (original: string, custom: string) => void
  onRemove: (original: string) => void
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
          <button onClick={() => onRemove(o)}>✕</button>
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

function ReleaseLogModal({
  open,
  version,
  releaseLog,
  loading,
  error,
  onClose,
}: {
  open: boolean
  version: string
  releaseLog: ReleaseLog | null
  loading: boolean
  error: string | null
  onClose: () => void
}) {
  useEffect(() => {
    if (!open) return
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  if (!open) return null
  const shownVersion = releaseLog?.version || version
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal release-log-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-log-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="release-log-header">
          <h3 id="release-log-title">Версия {shownVersion}</h3>
          <button type="button" className="icon-button" onClick={onClose} aria-label="Закрыть журнал релиза">×</button>
        </div>
        {loading && <p className="quality-empty">Загружаем журнал…</p>}
        {error && <div className="message error-message" role="alert">{error}</div>}
        {releaseLog && (
          <div className="release-log-content">
            <section>
              <h4>Реализовано в релизе</h4>
              <ul>{releaseLog.implemented.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
            <section>
              <h4>Осталось</h4>
              <ul>{releaseLog.remaining.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          </div>
        )}
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
  modal: { open: boolean; editIndex: number | null; name: string; position: string; pptx: string; prompt: string }
  productNames: string[]
  onChange: (patch: Partial<{ editIndex: number | null; name: string; position: string; pptx: string; prompt: string }>) => void
  onClose: () => void
  onSubmit: () => void
}) {
  const [dragOver, setDragOver] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const positions = ['first', 'end', ...productNames.flatMap((p) => [`before:${p}`, `after:${p}`])]

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
        <h3 id="static-slide-title">{modal.editIndex === null ? 'Новый статичный слайд' : 'Редактирование статичного слайда'}</h3>
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
        <label className="modal-field">
          Prompt для будущего AI-обновления:
          <textarea
            rows={5}
            value={modal.prompt}
            onChange={(e) => onChange({ prompt: e.target.value })}
            placeholder="Опишите назначение, содержание и требования к оформлению слайда"
          />
          <small>Сейчас prompt только сохраняется. Автоматическая генерация будет добавлена позже.</small>
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
          {modal.pptx ? `📎 ${modal.pptx} · кликните, чтобы заменить` : 'Перетащите .pptx сюда или кликните для выбора'}
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
        <small className="keep-source-format">Форматирование исходного слайда сохраняется (Keep Source Formatting).</small>
        {uploadError && <div className="error" role="alert">{uploadError}</div>}
        <div className="modal-actions">
          <button onClick={onClose}>Отмена</button>
          <button className="primary-button" onClick={onSubmit} disabled={!modal.pptx}>
            {modal.editIndex === null ? 'Добавить' : 'Сохранить'}
          </button>
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
      <div className="template-help">
        Для шаблона из трёх слайдов добавьте маркеры <code>_slide_type_product</code>,{' '}
        <code>_slide_type_stream</code> и <code>_slide_type_roadmap</code>. Заголовки:{' '}
        <code>product_name</code> и <code>stream_name</code>; на Roadmap-слайде обязательны{' '}
        <code>col_header</code> и <code>col_bullets</code>.
      </div>
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
  language,
  onPromptChange,
  onEdit,
  onDownload,
  onDelete,
}: {
  slides: { name: string; position: string; pptx: string; prompt: string; language: 'ru' | 'en' }[]
  language: 'ru' | 'en'
  onPromptChange: (index: number, prompt: string) => void
  onEdit: (index: number) => void
  onDownload: (filename: string) => void
  onDelete: (index: number) => void
}) {
  const visibleSlides = slides
    .map((slide, sourceIndex) => ({ slide, sourceIndex }))
    .filter(({ slide }) => (slide.language ?? 'ru') === language)
  if (visibleSlides.length === 0) {
    return <div className="priority-empty">Нет статичных слайдов для {language.toUpperCase()}.</div>
  }
  return (
    <div className="static-list">
      {visibleSlides.map(({ slide: s, sourceIndex }) => (
        <div key={sourceIndex} className="static-list-row">
          <span className="static-list-name">
            {s.name || '(без названия)'}
            <label className="static-prompt-editor">
              Prompt
              <textarea
                rows={3}
                value={s.prompt ?? ''}
                onChange={(event) => onPromptChange(sourceIndex, event.target.value)}
                placeholder="Опишите будущую AI-генерацию или обновление слайда"
              />
            </label>
          </span>
          <span className="static-list-pos">{positionLabel(s.position)}</span>
          <button title="Заменить файл или изменить позицию" onClick={() => onEdit(sourceIndex)}>
            Изменить
          </button>
          <button
            title="Скачать текущий PPTX"
            disabled={!s.pptx}
            onClick={() => onDownload(s.pptx)}
          >
            Скачать
          </button>
          <button title="Удалить" onClick={() => onDelete(sourceIndex)}>
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
  collapsedNodes,
  toggleNode,
  recentlyReorderedNodes,
  newTierPaths,
  productLanguages,
}: {
  slides: Slide[]
  tree: Tree | null
  dropHandlers: DropHandlerFactory
  newReqIds: Set<number>
  changedReqIds: Set<number>
  collapsedNodes: Set<string>
  toggleNode: (key: string) => void
  recentlyReorderedNodes: Set<string>
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

  const card = (slide: Slide, index: number) => (
    <SlideCard
      key={index}
      slide={slide}
      slideNumber={index + 1}
      newReqIds={newReqIds}
      changedReqIds={changedReqIds}
    />
  )

  const countLabel = (count: number, one: string, few: string, many: string) => {
    const mod100 = count % 100
    const mod10 = count % 10
    const word = mod100 >= 11 && mod100 <= 14 ? many : mod10 === 1 ? one : mod10 >= 2 && mod10 <= 4 ? few : many
    return `${count} ${word}`
  }

  const slidesCount = (tiers: TierNode[]) => tiers.reduce((total, tier) => total + tier.slides.length, 0)
  const featuresCount = (tiers: TierNode[]) => tiers.reduce((total, tier) => total + tierBulletCount(tier), 0)

  const renderTier = (productName: string, streamName: string, tier: TierNode, tierIndex: number, tierNames: string[]) => {
    if (!isRealNodeName(tier.tier)) {
      return (
        <div className="direct-roadmaps" key={`direct:${streamName}:${tierIndex}`}>
          {tier.slides.map((slide) => card(slide, slides.indexOf(slide)))}
        </div>
      )
    }
    const key = tierNodeKey(productName, streamName, tier.tier)
    const expanded = !collapsedNodes.has(key)
    const drag = dropHandlers(
      `${productName} > ${streamName}`,
      tierIndex,
      tierNames,
      tierNames.map((name) => tierNodeKey(productName, streamName, name)),
    )
    const summaryParts = [countLabel(tierBulletCount(tier), 'фича', 'фичи', 'фич')]
    if (tier.slides.length > 1) summaryParts.unshift(countLabel(tier.slides.length, 'слайд', 'слайда', 'слайдов'))
    return (
      <div key={tier.tier} className="group">
        <HierarchyHeader
          className="tier-h"
          badge="TIER"
          title={tier.tier}
          summary={summaryParts.join(' · ')}
          expanded={expanded}
          onToggle={() => toggleNode(key)}
          drag={drag}
          highlighted={recentlyReorderedNodes.has(key)}
        >
          {newTierPaths.has(`${productName} > ${streamName} > ${tier.tier}`) && (
            <span className="tree-badge">новое</span>
          )}
        </HierarchyHeader>
        {expanded && tier.slides.map((slide) => card(slide, slides.indexOf(slide)))}
      </div>
    )
  }

  const renderStream = (productName: string, stream: StreamNode, streamIndex: number, streamNames: string[]) => {
    const realTiers = stream.tiers.filter((tier) => isRealNodeName(tier.tier))
    const tierNames = realTiers.map((tier) => tier.tier)
    const children = () => stream.tiers.map((tier) =>
      renderTier(productName, stream.stream, tier, Math.max(0, tierNames.indexOf(tier.tier)), tierNames),
    )

    if (!isRealNodeName(stream.stream)) return <div className="implicit-group" key={`implicit:${streamIndex}`}>{children()}</div>

    const key = streamNodeKey(productName, stream.stream)
    const expanded = !collapsedNodes.has(key)
    const drag = dropHandlers(
      productName,
      streamIndex,
      streamNames,
      streamNames.map((name) => streamNodeKey(productName, name)),
    )
    const streamSlides = slidesCount(stream.tiers)
    const summary = realTiers.length
      ? `${countLabel(realTiers.length, 'тир', 'тира', 'тиров')} · ${countLabel(streamSlides, 'слайд', 'слайда', 'слайдов')}`
      : `${countLabel(streamSlides, 'слайд', 'слайда', 'слайдов')} · ${countLabel(featuresCount(stream.tiers), 'фича', 'фичи', 'фич')}`
    return (
      <div key={stream.stream} className="group">
        <HierarchyHeader
          className="stream-h"
          badge="STREAM"
          title={stream.stream}
          summary={summary}
          expanded={expanded}
          onToggle={() => toggleNode(key)}
          drag={drag}
          highlighted={recentlyReorderedNodes.has(key)}
        />
        {expanded && children()}
      </div>
    )
  }

  return (
    <div className="grouped">
      {top.filter((slide) => isStatic(slide) && slide.position === 'first')
        .map((slide) => card(slide, slides.indexOf(slide)))}
      {top.filter(isTitle).map((slide) => card(slide, slides.indexOf(slide)))}
      {products.map((product, productIndex) => {
        const key = productNodeKey(product.product)
        const expanded = !collapsedNodes.has(key)
        const realStreams = product.streams.filter((stream) => isRealNodeName(stream.stream))
        const realTiers = product.streams.flatMap((stream) => stream.tiers.filter((tier) => isRealNodeName(tier.tier)))
        const streamNames = realStreams.map((stream) => stream.stream)
        const productSlides = product.streams.reduce((total, stream) => total + slidesCount(stream.tiers), 0)
        const summaryParts = []
        if (realStreams.length) summaryParts.push(countLabel(realStreams.length, 'стрим', 'стрима', 'стримов'))
        if (realTiers.length) summaryParts.push(countLabel(realTiers.length, 'тир', 'тира', 'тиров'))
        summaryParts.push(countLabel(productSlides, 'слайд', 'слайда', 'слайдов'))
        const productNamesInOrder = products.map((item) => item.product)
        const drag = dropHandlers(
          '',
          productIndex,
          productNamesInOrder,
          productNamesInOrder.map(productNodeKey),
        )
        return (
          <div key={product.product} className="product-bundle">
            {top.filter((slide) => isStatic(slide) && slide.position === `before:${product.product}`)
              .map((slide) => card(slide, slides.indexOf(slide)))}
            <div className="group">
              <HierarchyHeader
                className="product-h"
                badge="PRODUCT"
                title={product.product}
                summary={summaryParts.join(' · ')}
                expanded={expanded}
                onToggle={() => toggleNode(key)}
                drag={drag}
                highlighted={recentlyReorderedNodes.has(key)}
              >
                {langLabel(product.product) && <span className="lang-badge">{langLabel(product.product)}</span>}
              </HierarchyHeader>
              {expanded && product.streams.map((stream) =>
                renderStream(
                  product.product,
                  stream,
                  Math.max(0, streamNames.indexOf(stream.stream)),
                  streamNames,
                ),
              )}
            </div>
            {top.filter((slide) => isStatic(slide) && slide.position === `after:${product.product}`)
              .map((slide) => card(slide, slides.indexOf(slide)))}
          </div>
        )
      })}
      {top.filter((slide) => isStatic(slide) && slide.position === 'end')
        .map((slide) => card(slide, slides.indexOf(slide)))}
      {top.filter(isThankYou).map((slide) => card(slide, slides.indexOf(slide)))}
    </div>
  )
}

function HierarchyHeader({
  className,
  badge,
  title,
  summary,
  expanded,
  onToggle,
  drag,
  highlighted,
  children,
}: {
  className: string
  badge: string
  title: string
  summary: string
  expanded: boolean
  onToggle: () => void
  drag: DragBinding
  highlighted: boolean
  children?: ReactNode
}) {
  return (
    <div {...drag.targetProps} className={`group-header ${className}${highlighted ? ' reorder-flash' : ''}`}>
      <button type="button" className="drag-handle" title="Перетащить или Alt + ↑/↓" {...drag.handleProps}>⠿</button>
      <button type="button" className="group-toggle" onClick={onToggle} aria-expanded={expanded}>
        <span className="node-chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        <span className="badge">{badge}</span>
        <span className="group-title">{title}</span>
        <span className="group-summary">{summary}</span>
      </button>
      {children}
    </div>
  )
}

function ProductSlideVisibilityPanel({
  productNames,
  hiddenFlags,
  onChange,
}: {
  productNames: string[]
  hiddenFlags: Record<string, boolean>
  onChange: (name: string, generate: boolean) => void
}) {
  return (
    <div className="product-slide-options">
      <div className="product-slide-help">
        Отключите автоматический слайд продукта, если вместо него используется статичный.
      </div>
      {productNames.map((name) => (
        <label key={name} className="product-slide-row">
          <input
            type="checkbox"
            checked={!hiddenFlags[name]}
            onChange={(event) => onChange(name, event.target.checked)}
          />
          <span title={name}>{name}</span>
        </label>
      ))}
    </div>
  )
}


function ProductLanguagesPanel({
  productNames,
  tierNames,
  languages,
  localizedTierNames,
  onChange,
  onTierNameChange,
}: {
  productNames: string[]
  tierNames: string[]
  languages: Record<string, { ru: boolean; en: boolean }>
  localizedTierNames: Record<string, { ru: string; en: string }>
  onChange: (name: string, lang: 'ru' | 'en', visible: boolean) => void
  onTierNameChange: (name: string, lang: 'ru' | 'en', value: string) => void
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
      {tierNames.length > 0 && <div className="tier-name-heading">Названия тиров для слайдов</div>}
      {tierNames.map((name) => {
        const localized = localizedTierNames[name] ?? { ru: '', en: '' }
        return (
          <div key={name} className="tier-name-row">
            <span className="product-lang-name" title={name}>{name}</span>
            <input
              type="text"
              aria-label={`Название ${name}, RU`}
              placeholder="RU: исходное"
              value={localized.ru}
              onChange={(e) => onTierNameChange(name, 'ru', e.target.value)}
            />
            <input
              type="text"
              aria-label={`Название ${name}, ENG`}
              placeholder="ENG: исходное"
              value={localized.en}
              onChange={(e) => onTierNameChange(name, 'en', e.target.value)}
            />
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
  accept = 'image/png,image/jpeg,image/webp,image/svg+xml,.svg',
  deleteTitle = 'Удалить логотип',
}: {
  productNames: string[]
  statuses: Record<string, ProductLogoStatus>
  onUpload: (name: string, file: File) => void
  onDelete: (name: string) => void
  accept?: string
  deleteTitle?: string
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
                <label className="logo-upload compact">
                  Заменить
                  <input
                    type="file"
                    accept={accept}
                    onChange={(e) => {
                      const f = e.target.files?.[0]
                      if (f) onUpload(name, f)
                      e.target.value = ''
                    }}
                  />
                </label>
                <button className="logo-delete" onClick={() => onDelete(name)} title={deleteTitle}>
                  ✕
                </button>
              </>
            ) : (
              <label className="logo-upload">
                Загрузить
                <input
                  type="file"
                  accept={accept}
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
}: {
  slide: Slide
  slideNumber?: number
  newReqIds: Set<number>
  changedReqIds: Set<number>
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
        <span className="title-sub">{positionLabel(slide.position)}</span>
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
    />
  )
}

function RoadmapCard({
  slide,
  slideNumber,
  newReqIds,
  changedReqIds,
}: {
  slide: RoadmapSlide
  slideNumber?: number
  newReqIds: Set<number>
  changedReqIds: Set<number>
}) {
  return (
    <div className="card roadmap">
      <div className="roadmap-head">
        {slideNumber && <span className="slide-number">{slideNumber}</span>}
        <span className="badge">{slide.continuation ? 'Roadmap (cont.)' : 'Roadmap'}</span>
      </div>
      <div className="columns">
        {slide.columns.map((col, i) => (
          <ColumnView
            key={i}
            col={col}
            showQuarterHeader={i === 0 || slide.columns[i - 1].quarter !== col.quarter}
            newReqIds={newReqIds}
            changedReqIds={changedReqIds}
          />
        ))}
      </div>
      {slide.footnote && <div className="footnote">{slide.footnote}</div>}
    </div>
  )
}

function ColumnView({
  col,
  showQuarterHeader,
  newReqIds,
  changedReqIds,
}: {
  col: Column
  showQuarterHeader: boolean
  newReqIds: Set<number>
  changedReqIds: Set<number>
}) {
  const bullets = col.grouped
    ? col.groups.flatMap((g) => g.bullets.map((b) => ({ b, group: g.app_title })))
    : col.bullets.map((b) => ({ b, group: null as string | null }))

  let lastGroup: string | null = null
  return (
    <div className="column">
      <div className="quarter">{showQuarterHeader ? col.quarter : '\u00a0'}</div>
      {showQuarterHeader && col.under_approval_badge && (
        <div className="approval-badge">{col.under_approval_badge}</div>
      )}
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
