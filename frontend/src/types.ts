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

export type Slide = RoadmapSlide | DividerSlide | TitleSlide | ThankYouSlide

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

export interface TreeTier {
  name: string
  inheritance_flag: boolean
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

export interface Profile {
  ordering: {
    order: Record<string, string[]>
    apptitle_priority: string[]
    tier_inheritance_flags: Record<string, boolean>
  }
  labels: Record<string, string>
  linter_rules: { pattern: string; description: string }[]
  under_approval_ids: number[]
  deck_meta: { title: string; year: string; version: string }
  service_strings: Record<string, { ru: string; en: string }>
  static_slides: { title: string; text: string; position: string }[]
}

export interface PlanResponse {
  errors: string[]
  warnings: string[]
  lint_issues: LintIssue[]
  plan: SlidePlan | null
  tree: Tree | null
  releases: ReleaseInfo[]
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
  new_tier_paths: string[]
  removed_tier_paths: string[]
}

export interface TemplateInfo {
  filename: string
  missing_shapes: string[]
  valid: boolean
  preview: string | null
  active: boolean
}
