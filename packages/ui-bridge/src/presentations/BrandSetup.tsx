import React, { useEffect, useState } from 'react'
import { presentationsApi, type Company } from './client'

const FONTS = ['Calibri', 'Cambria', 'Arial', 'Times New Roman']

/**
 * Company brand kit: logo, colours, fonts and footer. Each save is a new immutable version; decks
 * keep the version they were built with. The preview is an approximation; the real check is the
 * rendered PowerPoint of the first deck.
 */
export function BrandSetup({ company, onDone, onCancel }: { company: Company | null; onDone: (c: Company, warnings: string[]) => void; onCancel?: () => void }) {
  const kit = company?.activeBrand?.kit
  const [name, setName] = useState(company?.name ?? '')
  const [primary, setPrimary] = useState(kit?.palette.primary ?? '#1F3A93')
  const [accent, setAccent] = useState(kit?.palette.accent ?? '#0FA3B1')
  const [text, setText] = useState(kit?.palette.foreground ?? '#1B2333')
  const [head, setHead] = useState(kit?.typography.slide_title.family ?? 'Calibri')
  const [body, setBody] = useState(kit?.typography.body.family ?? 'Calibri')
  const [footer, setFooter] = useState(kit?.footer.text ?? '')
  const [pages, setPages] = useState(kit?.footer.show_page_number ?? true)
  const [logo, setLogo] = useState<File | null>(null)
  const [darkLogo, setDarkLogo] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!logo) return setPreview(null)
    const u = URL.createObjectURL(logo)
    setPreview(u)
    return () => URL.revokeObjectURL(u)
  }, [logo])

  async function save() {
    setBusy(true)
    setError('')
    try {
      let c = company
      if (!c) {
        const r = await presentationsApi.createCompany(name.trim())
        if (!r.ok) throw new Error(r.error)
        c = r.data
      }
      const upload = async (f: File | null) => {
        if (!f) return undefined
        const r = await presentationsApi.uploadLogo(c!.id, f)
        if (!r.ok) throw new Error(r.error)
        return r.data.id
      }
      const logoAssetId = (await upload(logo)) ?? kit?.logos.find((l) => l.variant !== 'dark_background')?.asset_id
      const darkLogoAssetId = (await upload(darkLogo)) ?? kit?.logos.find((l) => l.variant === 'dark_background')?.asset_id
      const r = await presentationsApi.createBrandKit(c.id, {
        palette: { primary, accent, foreground: text }, headingFont: head, bodyFont: body,
        footerText: footer.trim() || `${c.name} · Internal`, showPageNumber: pages, logoAssetId, darkLogoAssetId, activate: true,
      })
      if (!r.ok) throw new Error(r.error)
      const list = await presentationsApi.companies()
      const fresh = list.ok ? list.data.items.find((x) => x.id === c!.id) ?? c : c
      onDone(fresh, r.data.warnings)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Saving the brand failed.')
    } finally {
      setBusy(false)
    }
  }

  const color = (label: string, value: string, set: (v: string) => void) => (
    <label className="pz-color">
      <span>{label}</span>
      <input type="color" value={value} onChange={(e) => set(e.target.value.toUpperCase())} aria-label={`${label} colour`} />
      <input value={value} maxLength={7} onChange={(e) => set(e.target.value)} aria-label={`${label} hex`} />
    </label>
  )

  return (
    <section className="pz-panel" aria-label="Company brand">
      <h3>{company ? `Brand for ${company.name}` : 'Set up your company brand'}</h3>
      <p className="pz-muted">Every presentation uses these. Saving creates a new version; existing decks keep theirs.</p>
      <div className="pz-brand">
        <div className="pz-brand-form">
          {!company && (
            <label className="pz-field">
              Company name
              <input value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
            </label>
          )}
          <label className="pz-field">
            Logo (PNG or JPEG, transparent background works best)
            <input type="file" accept="image/png,image/jpeg" onChange={(e) => setLogo(e.target.files?.[0] ?? null)} />
          </label>
          <label className="pz-field">
            Logo for dark backgrounds (optional)
            <input type="file" accept="image/png,image/jpeg" onChange={(e) => setDarkLogo(e.target.files?.[0] ?? null)} />
          </label>
          <div className="pz-colors">
            {color('Main colour', primary, setPrimary)}
            {color('Accent', accent, setAccent)}
            {color('Text', text, setText)}
          </div>
          <div className="pz-row">
            <label className="pz-field">
              Heading font
              <select value={head} onChange={(e) => setHead(e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select>
            </label>
            <label className="pz-field">
              Body font
              <select value={body} onChange={(e) => setBody(e.target.value)}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select>
            </label>
          </div>
          <label className="pz-field">
            Footer text
            <input value={footer} maxLength={160} placeholder={`${name || company?.name || 'Company'} · Internal`} onChange={(e) => setFooter(e.target.value)} />
          </label>
          <label className="pz-check">
            <input type="checkbox" checked={pages} onChange={(e) => setPages(e.target.checked)} /> Show slide numbers
          </label>
        </div>
        <div className="pz-brand-preview" aria-label="Approximate preview">
          <div className="pz-mini pz-mini-cover" style={{ background: primary }}>
            {preview && <img src={preview} alt="" />}
            <strong style={{ fontFamily: head }}>Weekly review</strong>
            <span style={{ fontFamily: body }}>Week 40 · Status and decisions</span>
            <i style={{ background: accent }} />
          </div>
          <div className="pz-mini" style={{ color: text, fontFamily: body }}>
            <strong style={{ fontFamily: head }}>The week in numbers</strong>
            <div className="pz-mini-tiles">
              {['25', '3.2 d', '98%'].map((v) => (
                <span key={v} style={{ color: primary }}>{v}</span>
              ))}
            </div>
            <small>{footer || `${name || company?.name || 'Company'} · Internal`}</small>
          </div>
          <p className="pz-muted">Approximate preview. The real check is the rendered PowerPoint.</p>
        </div>
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="pz-actions">
        {onCancel && <button type="button" onClick={onCancel}>Cancel</button>}
        <button type="button" className="pz-primary" disabled={busy || (!company && !name.trim())} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save brand'}
        </button>
      </div>
    </section>
  )
}
