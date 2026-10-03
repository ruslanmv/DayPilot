import { api } from '../apiClient'

export type Slide = { id?: string; type: string; title: string; notes?: string; [k: string]: unknown }
export type Storyline = { schema_version: 'daypilot.storyline/v1'; title: string; subtitle?: string; audience?: string; purpose?: string; slides: Slide[]; [k: string]: unknown }
export type Finding = { severity: 'hard' | 'warning'; code: string; slide: string | null; element?: string; message: string }
export type RunInfo = { id: string; revision: number; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'; phase: string; error: string | null }
export type Revision = {
  revision: number
  parent: number | null
  state: 'queued' | 'composing' | 'review_ready' | 'failed' | 'approved'
  author: string
  brandVersion: number
  slideCount: number | null
  pptxSha256: string | null
  error: string | null
  createdAt: string | null
  approvedAt: string | null
  quality: { status: string; hard_failures: number; warnings: number; slides_checked: number } | null
  files: { pptx: boolean; pdf: boolean; slides: number }
  run: RunInfo | null
  locks: string[]
  expert?: boolean
  expertScript?: string | null
  storyline?: Storyline
  findings?: Finding[]
  notes?: { id: string; title: string; notes: string }[]
}
export type Deck = {
  id: string
  title: string
  companyId: string
  headRevision: number
  archived: boolean
  seriesId: string | null
  periodKey: string | null
  updatedAt: string | null
  head: Revision | null
  revisions?: Revision[]
  run?: RunInfo | null
  removedNumbers?: string[]
}
export type BrandKit = {
  palette: Record<string, string>
  typography: Record<string, { family: string; minimum_pt: number; preferred_pt: number }>
  footer: { text: string; show_page_number: boolean }
  logos: { asset_id: string; variant: string; aspect_ratio: number }[]
}
export type Company = {
  id: string
  name: string
  activeBrandVersion: number | null
  brandVersions: number
  activeBrand: { version: number; sha256: string; kit: BrandKit; warnings: string[] } | null
}
export type Capabilities = {
  enabled: boolean
  engine: boolean
  render: { ready: boolean; fonts: Record<string, boolean> }
  genres: { id: string; name: string }[]
  slideTypes: string[]
  fonts: string[]
  expert?: { enabled: boolean; ready: boolean }
}
export type Series = {
  id: string
  name: string
  companyId: string
  paused: boolean
  timezone: string
  nextPeriod: { key: string; label: string; start: string; end_exclusive: string } | null
  occurrences: { periodKey: string; deckId: string; start: string; end: string }[]
  schedule?: Schedule
}
export type Schedule = {
  enabled: boolean
  weekday: number | null
  localTime: string | null
  catchUpHours: number
  nextRunAt: string | null
  lastFiredAt: string | null
  lastResult: string | null
  upcoming: string[]
  schedulerRunning: boolean
  policy: string
}
export type TemplateReport = {
  kind: 'pptx' | 'potx'
  themeName: string | null
  slideSize: { width_inches: number; height_inches: number }
  palette: Record<string, string>
  fonts: { heading: string | null; body: string | null }
  footer: string | null
  kept: string[]
  notKept: string[]
  proposal: { palette: Record<string, string>; headingFont: string; bodyFont: string; footerText: string | null; warnings: string[] }
  logoCandidates: { index: number; part: string; mediaType: string; w: number; h: number }[]
  thumbnails: number
  rendered: boolean
  renderNote?: string
  fidelityNote: string
}
export type Template = { id: string; companyId: string; filename: string; sha256: string; bytes: number; createdAt: string | null; report: TemplateReport }
export type BrandChoices = {
  palette: Record<string, string>
  headingFont: string
  bodyFont: string
  footerText: string
  showPageNumber: boolean
  logoAssetId?: string
  darkLogoAssetId?: string
  activate?: boolean
  fromTemplateId?: string
  templateLogoIndex?: number
}

function headers() {
  const match = document.cookie.match(/(?:^|;\s*)dp_csrf=([^;]+)/)
  return { headers: { 'X-CSRF-Token': match ? decodeURIComponent(match[1]) : '' } }
}
const P = '/v1/presentations'
const e = encodeURIComponent

export const presentationsApi = {
  capabilities: () => api.get<Capabilities>(`${P}/capabilities`),
  companies: () => api.get<{ items: Company[] }>(`${P}/companies`),
  createCompany: (name: string) => api.post<Company>(`${P}/companies`, { name }, headers()),
  uploadLogo: (companyId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<{ id: string; width: number; height: number }>(`${P}/companies/${e(companyId)}/assets`, form, headers())
  },
  assetUrl: (id: string) => `${P}/assets/${e(id)}`,
  createBrandKit: (companyId: string, choices: BrandChoices) =>
    api.post<{ version: number; warnings: string[]; active: boolean }>(`${P}/companies/${e(companyId)}/brand-kits`, choices, headers()),
  activate: (companyId: string, version: number, expectedActiveVersion: number | null) =>
    api.post<{ activeBrandVersion: number }>(`${P}/companies/${e(companyId)}/brand-kits/${version}/activate`, { expectedActiveVersion }, headers()),
  starter: (genre: string, topic: string, periodLabel: string, audience: string) =>
    api.post<{ storyline: Storyline }>(`${P}/starter`, { genre, topic, periodLabel, audience }, headers()),
  outline: (body: { genre: string; brief: string; audience: string; slideCount: number; sources: string; diagramId?: string; periodLabel?: string }) =>
    api.post<{ storyline: Storyline; mode: 'model' | 'template'; removedNumbers: string[]; message?: string; credits?: { charged: number; balance: number } }>(`${P}/outline`, body, headers()),
  decks: (q = '') => api.get<{ items: Deck[] }>(`${P}/decks${q ? `?q=${e(q)}` : ''}`),
  deck: (id: string) => api.get<Deck>(`${P}/decks/${e(id)}`),
  revision: (id: string, n: number) => api.get<Revision>(`${P}/decks/${e(id)}/revisions/${n}`),
  createDeck: (companyId: string, storyline: Storyline) => api.post<Deck>(`${P}/decks`, { companyId, storyline }, headers()),
  revise: (id: string, storyline: Storyline, expectedRevision: number, locks: string[], rebrand = false) =>
    api.post<Deck>(`${P}/decks/${e(id)}/revisions`, { storyline, expectedRevision, locks, rebrand }, headers()),
  locks: (id: string, locks: string[], expectedRevision: number) => api.post<{ locks: string[] }>(`${P}/decks/${e(id)}/locks`, { locks, expectedRevision }, headers()),
  regenerate: (id: string, slideIds: string[], instruction: string, expectedRevision: number) =>
    api.post<Deck>(`${P}/decks/${e(id)}/regenerate`, { slideIds, instruction, expectedRevision }, headers()),
  restore: (id: string, revision: number, expectedRevision: number) => api.post<Deck>(`${P}/decks/${e(id)}/restore`, { revision, expectedRevision }, headers()),
  archive: (id: string) => api.post<{ archived: boolean }>(`${P}/decks/${e(id)}/archive`, {}, headers()),
  approve: (id: string, n: number, pptxSha256: string) => api.post<Revision>(`${P}/decks/${e(id)}/revisions/${n}/approve`, { pptxSha256 }, headers()),
  fileUrl: (id: string, n: number, kind: 'pptx' | 'pdf' | 'png', slide = 0) => `${P}/decks/${e(id)}/revisions/${n}/files/${kind}${kind === 'png' ? `?slide=${slide}` : ''}`,
  series: () => api.get<{ items: Series[] }>(`${P}/series`),
  createSeries: (body: { companyId: string; name: string; timezone: string; weekStartsOn: number; rule: string; storyline: Storyline }) =>
    api.post<Series>(`${P}/series`, body, headers()),
  prepare: (id: string) => api.post<{ created: boolean; period: { key: string; label: string }; deck: Deck }>(`${P}/series/${e(id)}/prepare`, {}, headers()),
  pause: (id: string) => api.post<Series>(`${P}/series/${e(id)}/pause`, {}, headers()),
  setSchedule: (id: string, body: { enabled: boolean; weekday: number; localTime: string; catchUpHours: number }) =>
    api.put<Series>(`${P}/series/${e(id)}/schedule`, body, headers()),
  importTemplate: (companyId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.postForm<Template>(`${P}/companies/${e(companyId)}/templates`, form, headers())
  },
  templates: (companyId: string) => api.get<{ items: Template[] }>(`${P}/companies/${e(companyId)}/templates`),
  templateThumbUrl: (id: string, n: number) => `${P}/templates/${e(id)}/thumbs/${n}`,
  templateLogoUrl: (id: string, index: number) => `${P}/templates/${e(id)}/logo/${index}`,
  templateFileUrl: (id: string) => `${P}/templates/${e(id)}/file`,
  expert: (id: string, script: string, expectedRevision: number) => api.post<Deck>(`${P}/decks/${e(id)}/expert`, { script, expectedRevision }, headers()),
  diagrams: () => api.get<{ items: { id: string; title: string }[] }>('/v1/diagrams?archived=exclude&limit=50'),
}
