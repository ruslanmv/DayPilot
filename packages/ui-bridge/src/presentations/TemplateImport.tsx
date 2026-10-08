import React, { useEffect, useState } from 'react'
import { presentationsApi, type Company, type Template } from './client'
import { download, useBlobUrl } from './files'

function Img({ path, alt }: { path: string; alt: string }) {
  const url = useBlobUrl(path)
  return url ? <img src={url} alt={alt} /> : <span className="pz-thumb-empty" />
}

/**
 * Import an existing .pptx/.potx: the original is kept byte for byte, and the report says plainly
 * what DayPilot uses from it (colours, fonts, size, footer, logo) and what it does not reproduce.
 */
export function TemplateImport({ company, onBrand }: { company: Company; onBrand: (warnings: string[]) => void }) {
  const [items, setItems] = useState<Template[]>([])
  const [open, setOpen] = useState<Template | null>(null)
  const [logo, setLogo] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    void presentationsApi.templates(company.id).then((r) => r.ok && setItems(r.data.items))
  }, [company.id])

  async function upload(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setError('')
    const r = await presentationsApi.importTemplate(company.id, file)
    setBusy(false)
    if (!r.ok) return setError(r.error)
    setItems((xs) => [r.data, ...xs.filter((x) => x.id !== r.data.id)])
    setOpen(r.data)
    setLogo(r.data.report.logoCandidates.find((c) => !c.mediaType.startsWith('unsupported'))?.index ?? null)
  }

  async function useTemplate(t: Template) {
    setBusy(true)
    setError('')
    const r = await presentationsApi.createBrandKit(company.id, {
      palette: {}, headingFont: '', bodyFont: '', footerText: '', showPageNumber: true, activate: true,
      fromTemplateId: t.id, ...(logo !== null ? { templateLogoIndex: logo } : {}),
    })
    setBusy(false)
    if (!r.ok) return setError(r.error)
    onBrand([...t.report.proposal.warnings, ...r.data.warnings])
  }

  const rep = open?.report
  return (
    <section className="pz-panel" aria-label="Import a PowerPoint template">
      <h3>Start from your PowerPoint template</h3>
      <p className="pz-muted">Upload a .pptx or .potx. DayPilot keeps the original file and uses its colours, fonts, slide size, footer and logo.</p>
      <label className="pz-field">
        Template file (.pptx or .potx, up to 50 MB)
        <input type="file" accept=".pptx,.potx,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.presentationml.template" disabled={busy} onChange={(e) => void upload(e.target.files?.[0])} />
      </label>
      {busy && <p role="status">Reading the template…</p>}
      {error && <p role="alert">{error}</p>}
      {items.length > 0 && !open && (
        <ul className="pz-series">
          {items.map((t) => (
            <li key={t.id}>
              <strong>{t.filename}</strong>
              <span className="pz-muted">{t.report.themeName ?? 'Theme'} · {t.report.slideSize.width_inches} × {t.report.slideSize.height_inches} in</span>
              <span className="pz-spacer" />
              <button type="button" onClick={() => { setOpen(t); setLogo(t.report.logoCandidates.find((c) => !c.mediaType.startsWith('unsupported'))?.index ?? null) }}>Review</button>
            </li>
          ))}
        </ul>
      )}
      {open && rep && (
        <div className="pz-grid" aria-label={`Template ${open.filename}`}>
          <h4>{open.filename}</h4>
          <p className="pz-note">{rep.fidelityNote}</p>
          <div className="pz-row">
            <div className="pz-field">
              <strong>Used</strong>
              <ul>{rep.kept.map((k) => <li key={k}>{k}</li>)}</ul>
            </div>
            <div className="pz-field">
              <strong>Not reproduced</strong>
              <ul>{rep.notKept.map((k) => <li key={k}>{k}</li>)}</ul>
            </div>
          </div>
          <div className="pz-row" aria-label="Proposed brand">
            {Object.entries(rep.proposal.palette).map(([k, v]) => (
              <span key={k} className="pz-chip"><i className="pz-swatch" style={{ background: v }} /> {k} {v}</span>
            ))}
            <span className="pz-chip">Headings: {rep.proposal.headingFont}</span>
            <span className="pz-chip">Body: {rep.proposal.bodyFont}</span>
          </div>
          {rep.proposal.warnings.map((w) => <p key={w} className="pz-muted">⚠ {w}</p>)}
          {rep.logoCandidates.length > 0 && (
            <fieldset className="pz-genres">
              <legend>Logo</legend>
              {rep.logoCandidates.filter((c) => !c.mediaType.startsWith('unsupported')).map((c) => (
                <label key={c.index} className={logo === c.index ? 'is-selected' : ''}>
                  <input type="radio" name="tpl-logo" checked={logo === c.index} onChange={() => setLogo(c.index)} />
                  {c.mediaType === 'image/svg+xml' ? <span>SVG {c.part.split('/').pop()}</span> : <span className="pz-logo-cand"><Img path={presentationsApi.templateLogoUrl(open.id, c.index)} alt={`Logo candidate ${c.index + 1}`} /></span>}
                </label>
              ))}
              <label className={logo === null ? 'is-selected' : ''}>
                <input type="radio" name="tpl-logo" checked={logo === null} onChange={() => setLogo(null)} /> No logo
              </label>
            </fieldset>
          )}
          {rep.thumbnails > 0 ? (
            <div className="pz-tpl-thumbs" aria-label="Template pages as rendered">
              {Array.from({ length: Math.min(rep.thumbnails, 12) }, (_, i) => <Img key={i} path={presentationsApi.templateThumbUrl(open.id, i + 1)} alt={`Template page ${i + 1}`} />)}
            </div>
          ) : (
            <p className="pz-muted">{rep.renderNote ?? 'No previews.'}</p>
          )}
          <div className="pz-actions">
            <button type="button" onClick={() => void download(presentationsApi.templateFileUrl(open.id), open.filename)}>Download original</button>
            <button type="button" onClick={() => setOpen(null)}>Close</button>
            <button type="button" className="pz-primary" disabled={busy} onClick={() => void useTemplate(open)}>Create brand from this template</button>
          </div>
        </div>
      )}
    </section>
  )
}
