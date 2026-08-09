/**
 * The real approval queue.
 *
 * The Approval Center is the product's central governance claim: nothing
 * sensitive happens without a human decision, and every decision is audited.
 * That is only true if the panel a human actually clicks is the same queue the
 * server enforces — a local list with local buttons would show an approval the
 * backend never sees, and record a decision nowhere.
 *
 * `/v1/approvals` and `/v1/approvals/{id}/decide` have existed since the
 * Approval Center batch, with RBAC on the decide path and an audit record per
 * decision. This is the client for them.
 */
import { api } from '../apiClient'
import { workspaceId } from '../env'
import { orderQueue, toApprovalRow, type ApprovalRow } from './approvalsQueue'

export * from './approvalsQueue'

type ServerApproval = Parameters<typeof toApprovalRow>[0]

export const approvalsApi = {
  async list(): Promise<{ ok: true; rows: ApprovalRow[] } | { ok: false; error: string }> {
    const r = await api.get<{ items?: ServerApproval[] }>(
      `/v1/approvals?workspaceId=${workspaceId()}&limit=50`,
    )
    if (!r.ok) return { ok: false, error: r.error }
    return { ok: true, rows: orderQueue((r.data.items || []).map(toApprovalRow)) }
  },

  async decide(
    id: string,
    decision: 'approved' | 'rejected',
    reason?: string,
  ): Promise<{ ok: true } | { ok: false; error: string }> {
    const r = await api.post<{ status?: string }>(`/v1/approvals/${id}/decide`, { decision, reason })
    return r.ok ? { ok: true } : { ok: false, error: r.error }
  },
}
