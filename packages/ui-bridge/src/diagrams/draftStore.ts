/**
 * Durable local drafts (batch B2). Work in progress and conflict copies live in IndexedDB,
 * isolated per account and workspace, so a reload, a crash or a second tab never loses edits.
 * Falls back to memory when the browser blocks storage; `durable` says which one is in use.
 */
import type { Diagram } from './dmind'

export type DraftRecord = {
  id: string
  kind: 'draft' | 'conflict'
  document: Diagram
  saved: { id: string; revision: number } | null
  updatedAt: number
  reason?: string
}
export type Entry = { key: string; record: DraftRecord }
export interface DraftStore {
  durable: boolean
  put(key: string, record: DraftRecord): Promise<void>
  get(key: string): Promise<DraftRecord | undefined>
  list(prefix: string): Promise<Entry[]>
  remove(key: string): Promise<void>
  removePrefix(prefix: string): Promise<void>
}

export const MAX_DRAFTS_PER_SCOPE = 20
export const SETTING_KEY = 'daypilot.dmind.drafts'

/** JSON-encoded tuples cannot collide whatever characters an account or workspace id contains. */
export const scopePrefix = (account: string, workspace: string) =>
  JSON.stringify([account, workspace]).slice(0, -1) + ','
export const draftKey = (account: string, workspace: string, id: string) =>
  JSON.stringify([account, workspace, id])

export class MemoryStore implements DraftStore {
  durable = false
  private rows = new Map<string, DraftRecord>()
  async put(key: string, record: DraftRecord) {
    this.rows.set(key, structuredClone(record))
  }
  async get(key: string) {
    const r = this.rows.get(key)
    return r && structuredClone(r)
  }
  async list(prefix: string) {
    return [...this.rows]
      .filter(([k]) => k.startsWith(prefix))
      .map(([key, record]) => ({ key, record: structuredClone(record) }))
  }
  async remove(key: string) {
    this.rows.delete(key)
  }
  async removePrefix(prefix: string) {
    for (const k of [...this.rows.keys()]) if (k.startsWith(prefix)) this.rows.delete(k)
  }
}

const DB = 'daypilot-dmind'
const STORE = 'drafts'
const wrap = <T>(req: IDBRequest<T>) =>
  new Promise<T>((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })

export class IndexedDbStore implements DraftStore {
  durable = true
  constructor(private db: IDBDatabase) {}
  private tx(mode: IDBTransactionMode) {
    return this.db.transaction(STORE, mode).objectStore(STORE)
  }
  async put(key: string, record: DraftRecord) {
    await wrap(this.tx('readwrite').put(record, key))
  }
  async get(key: string) {
    return (await wrap(this.tx('readonly').get(key))) as DraftRecord | undefined
  }
  async list(prefix: string) {
    const range = IDBKeyRange.bound(prefix, prefix + '￿')
    const store = this.tx('readonly')
    const [keys, values] = await Promise.all([wrap(store.getAllKeys(range)), wrap(store.getAll(range))])
    return keys.map((k, i) => ({ key: String(k), record: values[i] as DraftRecord }))
  }
  async remove(key: string) {
    await wrap(this.tx('readwrite').delete(key))
  }
  async removePrefix(prefix: string) {
    await wrap(this.tx('readwrite').delete(IDBKeyRange.bound(prefix, prefix + '￿')))
  }
}

/** IndexedDB when the browser allows it, otherwise memory (and `durable` is false). */
export async function openDraftStore(factory: IDBFactory | undefined = globalThis.indexedDB): Promise<DraftStore> {
  if (!factory) return new MemoryStore()
  try {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const open = factory.open(DB, 1)
      open.onupgradeneeded = () => open.result.createObjectStore(STORE)
      open.onsuccess = () => resolve(open.result)
      open.onerror = () => reject(open.error)
      open.onblocked = () => reject(new Error('blocked'))
    })
    return new IndexedDbStore(db)
  } catch {
    return new MemoryStore()
  }
}

/** Opt-out for shared machines: the person (or an admin build) can turn local drafts off. */
export function draftsEnabled(storage: Pick<Storage, 'getItem'> | undefined = safeLocal()): boolean {
  try {
    return storage?.getItem(SETTING_KEY) !== 'off'
  } catch {
    return true
  }
}
function safeLocal(): Storage | undefined {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export async function putDraft(store: DraftStore, account: string, workspace: string, record: DraftRecord) {
  await store.put(draftKey(account, workspace, record.id), record)
  // Bound what accumulates: only unsaved drafts are pruned, conflict copies are kept until resolved.
  const drafts = (await store.list(scopePrefix(account, workspace)))
    .filter((e) => e.record.kind === 'draft')
    .sort((a, b) => b.record.updatedAt - a.record.updatedAt)
  for (const old of drafts.slice(MAX_DRAFTS_PER_SCOPE)) await store.remove(old.key)
}
export async function listDrafts(store: DraftStore, account: string, workspace: string) {
  return (await store.list(scopePrefix(account, workspace)))
    .map((e) => e.record)
    .sort((a, b) => b.updatedAt - a.updatedAt)
}
export const removeDraft = (store: DraftStore, account: string, workspace: string, id: string) =>
  store.remove(draftKey(account, workspace, id))
export const clearScope = (store: DraftStore, account: string, workspace: string) =>
  store.removePrefix(scopePrefix(account, workspace))
/** Sign-out on a shared machine: nothing from any account is left behind. */
export const clearAllDrafts = (store: DraftStore) => store.removePrefix('[')

export async function clearAllLocalDrafts(): Promise<void> {
  try {
    await clearAllDrafts(await openDraftStore())
  } catch {
    /* storage unavailable: nothing was kept */
  }
}
