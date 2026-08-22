import type { DiffResponse, PlanResponse, Profile, TemplateInfo } from './types'

export async function fetchHealth(): Promise<{ status: string; version: string }> {
  const res = await fetch('/api/health')
  return res.json()
}

export async function fetchPlan(
  jsonData: unknown,
  language: string,
  pluginSettings: Record<string, unknown>,
): Promise<PlanResponse> {
  const res = await fetch('/api/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ json_data: jsonData, language, plugin_settings: pluginSettings }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function downloadPptx(
  jsonData: unknown,
  language: string,
  pluginSettings: Record<string, unknown>,
): Promise<void> {
  const res = await fetch('/api/pptx', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ json_data: jsonData, language, plugin_settings: pluginSettings }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'roadmap.pptx'
  a.click()
  URL.revokeObjectURL(url)
}

export async function fetchDiff(
  oldJson: unknown,
  newJson: unknown,
  language: string,
): Promise<DiffResponse> {
  const res = await fetch('/api/diff', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old_json: oldJson, new_json: newJson, language }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listTemplates(): Promise<TemplateInfo[]> {
  const res = await fetch('/api/templates')
  return res.json()
}

export async function uploadTemplate(file: File): Promise<TemplateInfo> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/templates/upload', { method: 'POST', body: form })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function uploadStaticSlidePptx(file: File): Promise<{ filename: string; extracted_title: string }> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/static-slides/pptx', { method: 'POST', body: form })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function setActiveTemplate(filename: string | null): Promise<void> {
  await fetch('/api/templates/active', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename }),
  })
}

export async function deleteTemplate(filename: string): Promise<void> {
  await fetch(`/api/templates/${encodeURIComponent(filename)}`, { method: 'DELETE' })
}

export async function getProfile(): Promise<Profile> {
  const res = await fetch('/api/profile')
  return res.json()
}

export async function saveProfile(profile: Profile): Promise<void> {
  await fetch('/api/profile', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })
}

export interface ProductLogoStatus {
  has_logo: boolean
  url: string | null
}

export async function uploadProductLogo(productName: string, file: File): Promise<{ filename: string; url: string | null }> {
  const form = new FormData()
  form.append('product_name', productName)
  form.append('file', file)
  const res = await fetch('/api/product-logos/upload', { method: 'POST', body: form })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getProductLogoStatuses(products: string[]): Promise<Record<string, ProductLogoStatus>> {
  const res = await fetch('/api/product-logos/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ products }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.logos as Record<string, ProductLogoStatus>
}

export async function deleteProductLogo(productName: string): Promise<void> {
  const res = await fetch(`/api/product-logos?product_name=${encodeURIComponent(productName)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}

export async function uploadTierLogo(tierName: string, file: File): Promise<{ filename: string; url: string | null }> {
  const form = new FormData()
  form.append('tier_name', tierName)
  form.append('file', file)
  const res = await fetch('/api/tier-logos/upload', { method: 'POST', body: form })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getTierLogoStatuses(tiers: string[]): Promise<Record<string, ProductLogoStatus>> {
  const res = await fetch('/api/tier-logos/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tiers }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const data = await res.json()
  return data.logos as Record<string, ProductLogoStatus>
}

export async function deleteTierLogo(tierName: string): Promise<void> {
  const res = await fetch(`/api/tier-logos?tier_name=${encodeURIComponent(tierName)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
}
