export type WorkspaceAppTitleMode = 'auto' | 'on' | 'off'
export type WorkspaceExpansionLevel = 'products' | 'streams' | 'tiers' | 'features' | 'custom'
export type WorkspaceBulkExpansionLevel = Exclude<WorkspaceExpansionLevel, 'custom'>

export interface WorkspaceSession {
  version: 2
  jsonData: unknown
  jsonText: string
  language: 'ru' | 'en'
  apptitleMode: WorkspaceAppTitleMode
  leftCollapsed: boolean
  rightCollapsed: boolean
  rightWidth: number
  collapsedNodes: string[]
  expansionLevel: WorkspaceExpansionLevel
  lastBulkExpansionLevel: WorkspaceBulkExpansionLevel
}

const LEGACY_STORAGE_KEY = 'roadmap-pptx.workspace.v1'
const DATABASE_NAME = 'roadmap-pptx'
const DATABASE_VERSION = 1
const STORE_NAME = 'workspace'
const SESSION_KEY = 'current'

function normalizeWorkspaceSession(value: unknown): WorkspaceSession | null {
  if (!value || typeof value !== 'object') return null
  const saved = value as Record<string, unknown>
  if (saved.version !== 1 && saved.version !== 2) return null
  const language = saved.language === 'en' ? 'en' : 'ru'
  const apptitleMode: WorkspaceAppTitleMode =
    saved.apptitleMode === 'on' || saved.apptitleMode === 'off' ? saved.apptitleMode : 'auto'
  const rightWidth = typeof saved.rightWidth === 'number'
    ? Math.max(240, Math.min(600, saved.rightWidth))
    : 320
  return {
    version: 2,
    jsonData: saved.jsonData ?? null,
    jsonText: typeof saved.jsonText === 'string' ? saved.jsonText : '',
    language,
    apptitleMode,
    leftCollapsed: saved.leftCollapsed === true,
    rightCollapsed: saved.rightCollapsed === true,
    rightWidth,
    collapsedNodes: Array.isArray(saved.collapsedNodes)
      ? saved.collapsedNodes.filter((item): item is string => typeof item === 'string')
      : [],
    expansionLevel:
      saved.expansionLevel === 'products' || saved.expansionLevel === 'streams' ||
      saved.expansionLevel === 'tiers' || saved.expansionLevel === 'features' ||
      saved.expansionLevel === 'custom'
        ? saved.expansionLevel
        : 'features',
    lastBulkExpansionLevel:
      saved.lastBulkExpansionLevel === 'products' || saved.lastBulkExpansionLevel === 'streams' ||
      saved.lastBulkExpansionLevel === 'tiers' || saved.lastBulkExpansionLevel === 'features'
        ? saved.lastBulkExpansionLevel
        : 'features',
  }
}

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION)
    request.onerror = () => reject(request.error ?? new Error('Не удалось открыть IndexedDB'))
    request.onupgradeneeded = () => {
      const database = request.result
      if (!database.objectStoreNames.contains(STORE_NAME)) database.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
  })
}

async function runTransaction<T>(
  mode: IDBTransactionMode,
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const database = await openDatabase()
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, mode)
      const request = action(transaction.objectStore(STORE_NAME))
      let result: T
      request.onsuccess = () => { result = request.result }
      request.onerror = () => reject(request.error ?? new Error('Ошибка IndexedDB'))
      transaction.oncomplete = () => resolve(result)
      transaction.onabort = () => reject(transaction.error ?? new Error('Транзакция IndexedDB отменена'))
      transaction.onerror = () => reject(transaction.error ?? new Error('Ошибка транзакции IndexedDB'))
    })
  } finally {
    database.close()
  }
}

export async function readWorkspaceSession(): Promise<WorkspaceSession | null> {
  const stored = await runTransaction('readonly', (store) => store.get(SESSION_KEY))
  const session = normalizeWorkspaceSession(stored)
  if (session) return session

  let legacyRaw: string | null
  try {
    legacyRaw = localStorage.getItem(LEGACY_STORAGE_KEY)
  } catch {
    return null
  }
  if (!legacyRaw) return null
  let legacySession: WorkspaceSession | null
  try {
    legacySession = normalizeWorkspaceSession(JSON.parse(legacyRaw))
  } catch {
    legacySession = null
  }
  if (!legacySession) {
    localStorage.removeItem(LEGACY_STORAGE_KEY)
    return null
  }
  try {
    await saveWorkspaceSession(legacySession)
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch {
    // Не удаляем рабочую legacy-сессию, если миграция временно не удалась.
  }
  return legacySession
}

export async function saveWorkspaceSession(session: WorkspaceSession): Promise<void> {
  await runTransaction('readwrite', (store) => store.put(session, SESSION_KEY))
}

export async function clearWorkspaceSession(): Promise<void> {
  await runTransaction('readwrite', (store) => store.delete(SESSION_KEY))
  localStorage.removeItem(LEGACY_STORAGE_KEY)
}
