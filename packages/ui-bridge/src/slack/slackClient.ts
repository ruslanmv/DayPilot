/**
 * The live Slack workspace client.
 *
 * Deliberately **not** built on the seeded `INTEGRATIONS` array in
 * `settings/settingsData.ts`. That list is presentation copy for the
 * Integrations page; treating it as the source of truth would mean the Slack
 * workspace showed "connected" because a hardcoded row said so.
 *
 * There is also no `chat.postMessage` here and there never will be. `send()`
 * asks the gateway to open an approval; the only code that talks to Slack's
 * write API is the provider adapter behind the Integration Gateway.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'
import type {
  SlackDraft,
  SlackInboxItem,
  SlackCounts,
  SlackPreferences,
  SlackProposal,
  SlackSettingsPayload,
  SlackStatus,
  SlackThread,
  SlackConversation,
  TransformId,
} from './slackTypes'

export type Result<T> = { ok: true; data: T } | { ok: false; error: string; status?: number }

const ws = () => encodeURIComponent(workspaceId())

/** The gateway's "this deployment does not have the feature" answer. */
export const DISABLED = 'slack_workspace_disabled'

function unwrap<T>(r: Awaited<ReturnType<typeof api.get<T>>>): Result<T> {
  if (r.ok) return { ok: true, data: r.data }
  return { ok: false, error: r.error, status: r.status }
}

export const slackApi = {
  /** Reachable even when the feature is off; reports `enabled: false`. */
  async status(): Promise<Result<SlackStatus>> {
    return unwrap(await api.get<SlackStatus>(`/v1/slack/status?workspaceId=${ws()}`))
  },

  async settings(): Promise<Result<SlackSettingsPayload>> {
    return unwrap(await api.get<SlackSettingsPayload>(`/v1/slack/settings?workspaceId=${ws()}`))
  },

  async saveSettings(patch: Partial<SlackPreferences>): Promise<Result<SlackPreferences>> {
    const r = await api.put<{ settings: SlackPreferences }>(
      `/v1/slack/settings?workspaceId=${ws()}`, patch,
    )
    return r.ok ? { ok: true, data: r.data.settings } : { ok: false, error: r.error, status: r.status }
  },

  async inbox(group: string = 'all'): Promise<Result<{ items: SlackInboxItem[]; counts: SlackCounts }>> {
    return unwrap(await api.get<{ items: SlackInboxItem[]; counts: SlackCounts }>(
      `/v1/slack/inbox?workspaceId=${ws()}&group=${encodeURIComponent(group)}`,
    ))
  },

  async conversation(id: string): Promise<Result<SlackThread>> {
    return unwrap(await api.get<SlackThread>(`/v1/slack/conversations/${encodeURIComponent(id)}`))
  },

  async recipients(): Promise<Result<SlackConversation[]>> {
    const r = await api.get<{ items: SlackConversation[] }>(`/v1/slack/recipients?workspaceId=${ws()}`)
    return r.ok ? { ok: true, data: r.data.items } : { ok: false, error: r.error, status: r.status }
  },

  async markHandled(messageId: string, handled: boolean): Promise<Result<unknown>> {
    return unwrap(await api.post(`/v1/slack/messages/${encodeURIComponent(messageId)}/handled`, { handled }))
  },

  /** Draft a reply on demand — for when you disagree with the classifier. */
  async draftReply(conversationId: string, messageId: string | null): Promise<Result<SlackDraft>> {
    return unwrap(await api.post<SlackDraft>(
      `/v1/slack/conversations/${encodeURIComponent(conversationId)}/draft`,
      { workspaceId: workspaceId(), messageId },
    ))
  },

  async compose(body: {
    channelId?: string
    conversationId?: string
    kind?: string
    name?: string
    counterpart?: string
    audience?: string
    instruction?: string
  }): Promise<Result<{ conversation: SlackConversation; draft: SlackDraft }>> {
    return unwrap(await api.post<{ conversation: SlackConversation; draft: SlackDraft }>(
      '/v1/slack/compose', { workspaceId: workspaceId(), ...body },
    ))
  },

  async saveDraft(draftId: string, text: string): Promise<Result<SlackDraft>> {
    return unwrap(await api.patch<SlackDraft>(`/v1/slack/drafts/${encodeURIComponent(draftId)}`, { text }))
  },

  async transform(draftId: string, kind: TransformId): Promise<Result<SlackDraft>> {
    return unwrap(await api.post<SlackDraft>(
      `/v1/slack/drafts/${encodeURIComponent(draftId)}/transform`, { kind },
    ))
  },

  /**
   * Ask for a rewrite. Returns a *proposal*; the draft is untouched until
   * `accept`. This split is the reason the assistant is safe to experiment with.
   */
  async refine(draftId: string, instruction: string): Promise<Result<SlackProposal>> {
    return unwrap(await api.post<SlackProposal>(
      `/v1/slack/drafts/${encodeURIComponent(draftId)}/refine`, { instruction },
    ))
  },

  /** "Use this" — apply a proposal, keeping the previous text for Undo. */
  async accept(draftId: string, text: string, instruction: string): Promise<Result<SlackDraft>> {
    return unwrap(await api.post<SlackDraft>(
      `/v1/slack/drafts/${encodeURIComponent(draftId)}/accept`, { text, instruction },
    ))
  },

  async undo(draftId: string): Promise<Result<SlackDraft>> {
    return unwrap(await api.post<SlackDraft>(`/v1/slack/drafts/${encodeURIComponent(draftId)}/undo`))
  },

  /**
   * Request delivery. Resolves to `approval_required` — never to "sent".
   * If this ever returns a Slack timestamp, something upstream is wrong.
   */
  async send(draftId: string): Promise<Result<{ status: string; approvalId: string | null }>> {
    return unwrap(await api.post<{ status: string; approvalId: string | null }>(
      `/v1/slack/drafts/${encodeURIComponent(draftId)}/send`, { workspaceId: workspaceId() },
    ))
  },

  async discard(draftId: string): Promise<Result<SlackDraft>> {
    return unwrap(await api.del<SlackDraft>(`/v1/slack/drafts/${encodeURIComponent(draftId)}`))
  },
}

/** Turn a failed call into a sentence a person can act on. */
export function explain(error: string, status?: number): string {
  if (error === DISABLED || status === 404) {
    return 'The Slack workspace is not enabled on this deployment.'
  }
  if (status === 409) return 'This draft has moved on — reload the conversation.'
  if (error === 'gateway_html_response') return 'The API gateway did not answer. Check that it is running.'
  if (error === 'network_error' || error.includes('fetch')) return "Can't reach DayPilot right now."
  return error
}
