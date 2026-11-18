export interface Bullet {
  requirement_id: number
  text: string
  kbr: string | null
  app_title: string
  quarter: string
  is_subject_to_change: boolean
  release_id: number
}

export interface Group {
  app_title: string
  bullets: Bullet[]
}

export interface Column {
  quarter: string
  bullets: Bullet[]
  groups: Group[]
  grouped: boolean
  under_approval_badge: string
}

export interface RoadmapSlide {
  product: string
  stream: string
  tier: string
  columns: Column[]
  continuation: boolean
  has_subject_to_change: boolean
  footnote: string
  inheritance_note: string
}

export interface DividerSlide {
  divider_type: string
  title: string
}

export interface TitleSlide {
  title: string
  year: string
  version: string
}

export interface ThankYouSlide {
  text: string
}

export interface StaticSlide {
  name: string
  pptx: string
  prompt: string
  language: 'ru' | 'en'
  position: string
}

export type Slide = RoadmapSlide | DividerSlide | TitleSlide | ThankYouSlide | StaticSlide

export interface SlidePlan {
  slides: Slide[]
  conflicts: string[]
}

export interface LintIssue {
  product: string
  stream: string
  tier: string
  requirement_id: number
  text: string
  message: string
}

export interface QualityIssue {
  code: string
  severity: 'warning' | 'error'
  message: string
  release_id: number
  rpp_title: string
  trdate: string
  quarter: string
  product: string
  stream: string
  tier: string
  requirement_id?: number
  requirement_title?: string
  language?: 'ru' | 'en'
  field?: 'MarketingTitle' | 'MarketingTitleEn'
}

export interface TreeTier {
  name: string
}

export interface TreeStream {
  name: string
  tiers: TreeTier[]
}

export interface TreeProduct {
  name: string
  streams: TreeStream[]
}

export interface Tree {
  products: TreeProduct[]
}

export interface ReleaseInfo {
  id: number
  title: string
  app_title: string
  quarter: string
  product: string
  stream: string
  tier: string
}

export interface ReportItem {
  id: string | null
  title: string
  tfs_url: string | null
}

export interface ReleaseReportItem extends ReportItem {
  trdate: string
}

export interface OnlyRuReportItem extends ReportItem {
  marketing_title: string
  matched_terms: string[]
}

export interface ReportGroup<Item extends ReportItem = ReportItem> {
  name: string
  count: number
  items: Item[]
}

export interface ReportSection<Item extends ReportItem = ReportItem> {
  count: number
  groups: ReportGroup<Item>[]
}

export interface YearReport {
  totals: {
    requirements: number
    releases: number
  }
  missing_applicable: ReportSection
  missing_crdate: ReportSection<ReleaseReportItem>
  only_ru: ReportSection<OnlyRuReportItem>
}

export interface EnglishNameIssue {
  product: string
  stream: string
  tier: string
  release_id: number | string | null
  release_title: string
  requirement_id: string | null
  marketing_title_en: string
  matched_terms: string[]
}

export interface JsonReport {
  years: Record<'2026' | '2027', YearReport>
  english_name_issues: EnglishNameIssue[]
  terms: string[]
}

export interface ReleaseLog {
  version: string
  implemented: string[]
  remaining: string[]
}

export interface Profile {
  ordering: {
    order: Record<string, string[]>
    apptitle_priority: string[]
    product_inheritance_flags: Record<string, boolean>
    product_slide_hidden_flags: Record<string, boolean>
    product_slide_hidden_flags_by_language?: Record<'ru' | 'en', Record<string, boolean>>
  }
  labels: Record<string, string>
  linter_rules: { pattern: string; description: string }[]
  under_approval_ids: number[]
  deck_meta: {
    title: string
    year: string
    version: string
    include_title_slide: boolean
    include_thank_you_slide: boolean
    thank_you_text: { ru: string; en: string }
  }
  service_strings: Record<string, { ru: string; en: string }>
  static_slides: { name: string; position: string; pptx: string; prompt: string; language: 'ru' | 'en' }[]
  product_languages: Record<string, { ru: boolean; en: boolean }>
  tier_names: Record<string, { ru: string; en: string }>
  report_terms: string[]
}

export interface PlanResponse {
  errors: string[]
  warnings: string[]
  lint_issues: LintIssue[]
  quality_issues: QualityIssue[]
  plan: SlidePlan | null
  tree: Tree | null
  releases: ReleaseInfo[]
  report: JsonReport
}

export interface DiffResult {
  new_release_ids: number[]
  changed_release_ids: number[]
  removed_release_ids: number[]
  new_requirement_ids: number[]
  changed_requirement_ids: number[]
  removed_requirement_ids: number[]
}

export interface DiffResponse {
  diff: DiffResult
  details: Record<string, DiffDetail[]>
  new_tier_paths: string[]
  removed_tier_paths: string[]
}

export interface DiffDetail {
  id: number
  path: string
  before_path?: string
  title?: string
  quarter?: string
  text?: string
  kbr?: string | null
  changes?: Record<string, { before: unknown; after: unknown }>
}

export interface TemplateInfo {
  filename: string
  missing_shapes: string[]
  duplicate_shapes: string[]
  issues: string[]
  valid: boolean
  preview: string | null
  active: boolean
}
