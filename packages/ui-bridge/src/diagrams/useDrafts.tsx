import { useCallback, useEffect, useRef, useState } from 'react'
import {
  SETTING_KEY,
  clearScope,
  draftsEnabled,
  listDrafts,
  openDraftStore,
  putDraft,
  removeDraft,
  type DraftRecord,
  type DraftStore,
} from './draftStore'

/** Owns the IndexedDB draft store for one account and workspace (batch B2). */
export function useDrafts(account: string, workspace: string) {
  const store = useRef<DraftStore | null>(null)
  const [drafts, setDrafts] = useState<DraftRecord[]>([])
  const [ready, setReady] = useState(false)
  const [durable, setDurable] = useState(true)
  const [enabled, setEnabledState] = useState(() => draftsEnabled())

  const channel = useRef<BroadcastChannel | null>(null)
  const refresh = useCallback(async () => {
    if (store.current) setDrafts(await listDrafts(store.current, account, workspace))
  }, [account, workspace])
  // Other tabs of this browser announce changes so every tab's list stays current.
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return
    const c = new BroadcastChannel('daypilot-dmind-drafts')
    c.onmessage = () => void refresh()
    channel.current = c
    return () => {
      c.close()
      channel.current = null
    }
  }, [refresh])

  useEffect(() => {
    let live = true
    void openDraftStore().then(async (s) => {
      if (!live) return
      store.current = s
      setDurable(s.durable)
      setReady(true)
      setDrafts(await listDrafts(s, account, workspace))
    })
    return () => {
      live = false
    }
  }, [account, workspace])

  const save = useCallback(
    async (record: DraftRecord) => {
      if (!store.current || !enabled) return
      await putDraft(store.current, account, workspace, record)
      channel.current?.postMessage('changed')
      await refresh()
    },
    [account, workspace, enabled, refresh],
  )
  const discard = useCallback(
    async (id: string) => {
      if (!store.current) return
      await removeDraft(store.current, account, workspace, id)
      channel.current?.postMessage('changed')
      await refresh()
    },
    [account, workspace, refresh],
  )
  const setEnabled = useCallback(
    async (on: boolean) => {
      try {
        localStorage.setItem(SETTING_KEY, on ? 'on' : 'off')
      } catch {
        /* the choice then applies to this tab only */
      }
      setEnabledState(on)
      if (!on && store.current) {
        await clearScope(store.current, account, workspace)
        await refresh()
      }
    },
    [account, workspace, refresh],
  )
  return { ready, durable, enabled, drafts, save, discard, setEnabled, refresh }
}
