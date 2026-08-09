/**
 * Reading the approval queue.
 *
 * The Approval Center is the product's central governance claim: nothing
 * sensitive happens without a human decision, and every decision is audited.
 * How a row is presented is part of that claim — an unfamiliar risk level must
 * not read as harmless, and the queue must order itself as a to-do list rather
 * than a log — so those rules live here, as pure functions with no imports,
 * and are tested directly.
 */
export type ApprovalRisk = 'low' | 'medium' | 'high'
export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

export type ApprovalRow = {
  id: string
  action: string
  summary: string
  risk: ApprovalRisk
  resourceType: string
  status: ApprovalStatus
  createdAt?: string | null
  decidedAt?: string | null
}

type ServerApproval = {
  id: string
  action: string
  summary: string
  risk?: string
  status?: string
  resourceType?: string
  createdAt?: string | null
  decidedAt?: string | null
}

const RISKS: ApprovalRisk[] = ['low', 'medium', 'high']
const STATUSES: ApprovalStatus[] = ['pending', 'approved', 'rejected']

export function toApprovalRow(a: ServerApproval): ApprovalRow {
  const risk = (a.risk || 'low').toLowerCase() as ApprovalRisk
  const status = (a.status || 'pending').toLowerCase() as ApprovalStatus
  return {
    id: a.id,
    action: a.action,
    summary: a.summary || '',
    // An unrecognised risk must not read as low: the whole point of the badge
    // is that a human can trust it at a glance.
    risk: RISKS.includes(risk) ? risk : 'high',
    resourceType: a.resourceType || '',
    status: STATUSES.includes(status) ? status : 'pending',
    createdAt: a.createdAt ?? null,
    decidedAt: a.decidedAt ?? null,
  }
}

/** Pending first, then most recent — the queue is a to-do list, not a log. */
export function orderQueue(rows: ApprovalRow[]): ApprovalRow[] {
  const rank = (r: ApprovalRow) => (r.status === 'pending' ? 0 : 1)
  const riskRank = (r: ApprovalRow) => RISKS.length - 1 - RISKS.indexOf(r.risk)
  return rows.slice().sort((a, b) =>
    rank(a) - rank(b) ||
    riskRank(a) - riskRank(b) ||
    (b.createdAt || '').localeCompare(a.createdAt || ''),
  )
}
