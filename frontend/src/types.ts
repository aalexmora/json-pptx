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

export interface ReleaseProblem {
  release_id: number | null
  title: string
  product: string
  stream: string
  tier: string
  trdate: string | null
  crdate: string | null
  tfs_url: string | null
  codes: string[]
}

export interface YearReport {
  requirements: {
    unique: number
    occurrences: number
    reused: number
    duplicate_occurrences: number
  }
  releases: {
    total: number
    with_problems: number
    missing_crdate: number
    invalid_crdate: number
    invalid_trdate: number
    missing_app_title: number
    empty_requirements: number
  }
  release_problems: ReleaseProblem[]
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
}

export interface PublicFeatureRequirement {
  req_id: string
  title: string
}

export interface PublicFeatureProduct {
  product: string
  public: number
  mapped: number
  unmapped: number
  requirements: PublicFeatureRequirement[]
}

export interface PublicFeaturesReport {
  filename: string
  data_rows: number
  invalid_req_id_rows: number
  public_features: number
  mapped_public_features: number
  unmapped_public_features: number
  mapped_percent: number
  products: PublicFeatureProduct[]
  complete_products_by_year: Record<'2026' | '2027', string[]>
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
