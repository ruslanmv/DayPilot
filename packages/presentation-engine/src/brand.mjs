/**
 * Brand kits (daypilot.brand-kit/v1): validation, colour maths and the PowerPoint theme they imply.
 * A kit is data only; logos are referenced by asset id + SHA-256 and resolved by the caller.
 */
import { hasMetrics } from './fit.mjs'

export const ROLES = ['deck_title', 'slide_title', 'body', 'data', 'footnote']
export const ROLE_FLOOR = { deck_title: 28, slide_title: 24, body: 14, data: 12, footnote: 9 }
const HEX = /^#?[0-9A-Fa-f]{6}$/
const PALETTE = ['background', 'foreground', 'primary', 'accent', 'muted', 'positive', 'warning', 'negative']

export class SpecError extends Error {
  constructor(problems) {
    super(problems.join('; '))
    this.problems = problems
  }
}

export const hex = (c) => String(c).replace('#', '').toUpperCase()

function lin(v) {
  const s = v / 255
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
}
export function luminance(c) {
  const h = hex(c)
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16))
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}
/** WCAG contrast ratio between two colours (1..21). */
export function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
/** The more readable of near-white and the kit's foreground on a given background. */
export function onColor(bg, kit) {
  return contrast(bg, 'FFFFFF') >= contrast(bg, kit.palette.foreground) ? 'FFFFFF' : hex(kit.palette.foreground)
}
/** Mix a colour toward white (t=0 unchanged, t=1 white), for tints and subtle panels. */
export function tint(c, t) {
  const h = hex(c)
  return [0, 2, 4]
    .map((i) => Math.round(parseInt(h.slice(i, i + 2), 16) + (255 - parseInt(h.slice(i, i + 2), 16)) * t))
    .map((v) => v.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase()
}

export function validateBrandKit(kit) {
  const p = []
  if (!kit || typeof kit !== 'object') throw new SpecError(['brand kit must be an object'])
  if (kit.schema_version !== 'daypilot.brand-kit/v1') p.push('schema_version must be daypilot.brand-kit/v1')
  for (const k of ['id', 'company_id']) if (typeof kit[k] !== 'string' || !kit[k]) p.push(`${k} is required`)
  if (!Number.isInteger(kit.version) || kit.version < 1) p.push('version must be a positive integer')
  const size = kit.slide_size
  if (!size || !(size.width_inches >= 4 && size.width_inches <= 56) || !(size.height_inches >= 3 && size.height_inches <= 56))
    p.push('slide_size must be within 4-56 by 3-56 inches')
  for (const k of PALETTE) if (!HEX.test(kit.palette?.[k] ?? '')) p.push(`palette.${k} must be a hex colour`)
  for (const r of ROLES) {
    const t = kit.typography?.[r]
    if (!t || typeof t.family !== 'string' || !t.family) {
      p.push(`typography.${r}.family is required`)
      continue
    }
    if (!(t.minimum_pt >= ROLE_FLOOR[r]) || !(t.preferred_pt >= t.minimum_pt) || t.preferred_pt > 96)
      p.push(`typography.${r}: minimum ≥ ${ROLE_FLOOR[r]} pt and minimum ≤ preferred ≤ 96`)
    if (Array.isArray(kit.allowed_fonts) && !kit.allowed_fonts.includes(t.family)) p.push(`typography.${r}.family ${t.family} is not in allowed_fonts`)
  }
  for (const l of kit.logos ?? []) {
    if (!/^[0-9a-f]{64}$/.test(l.sha256 ?? '')) p.push(`logo ${l.asset_id}: sha256 required`)
    if (!(l.aspect_ratio > 0.1 && l.aspect_ratio < 20)) p.push(`logo ${l.asset_id}: aspect_ratio out of range`)
    if (!['universal', 'light_background', 'dark_background'].includes(l.variant)) p.push(`logo ${l.asset_id}: unknown variant`)
  }
  for (const c of kit.chart_style?.series_colors ?? []) if (!HEX.test(c)) p.push('chart_style.series_colors must be hex colours')
  if (kit.footer && typeof kit.footer.text !== 'string') p.push('footer.text must be text')
  if (kit.footer && kit.footer.text.length > 160) p.push('footer.text is limited to 160 characters')
  if (p.length) throw new SpecError(p)
  return kit
}

/** Problems that do not invalidate the kit but must be visible before activation. */
export function brandWarnings(kit) {
  const w = []
  const pal = kit.palette
  if (contrast(pal.foreground, pal.background) < 4.5) w.push(`Body text contrast ${contrast(pal.foreground, pal.background).toFixed(1)}:1 is below 4.5:1.`)
  for (const k of ['primary', 'accent']) {
    const best = Math.max(contrast(pal[k], 'FFFFFF'), contrast(pal[k], pal.foreground))
    if (best < 4.5) w.push(`No readable text colour on ${k} (${best.toFixed(1)}:1).`)
  }
  if (contrast(pal.muted, pal.background) < 4.5) w.push(`Muted text contrast ${contrast(pal.muted, pal.background).toFixed(1)}:1 is below 4.5:1; it is used for small print.`)
  const fonts = new Set(ROLES.map((r) => kit.typography[r].family))
  for (const f of fonts) if (!hasMetrics(f)) w.push(`Font "${f}" has no installed metric-compatible font in the renderer, so text fit cannot be verified; viewers without it will see a substitute.`)
  if (!(kit.logos ?? []).length) w.push('No logo: decks will carry the footer text only.')
  return w
}

/** The twelve theme slots written into ppt/theme/theme1.xml. */
export function themeColors(kit) {
  const p = kit.palette
  const series = (kit.chart_style?.series_colors ?? []).map(hex)
  const accents = [hex(p.primary), hex(p.accent), ...series.filter((c) => c !== hex(p.primary) && c !== hex(p.accent)), hex(p.positive), hex(p.warning), hex(p.negative), hex(p.muted)]
  return {
    dk1: hex(p.foreground), lt1: hex(p.background), dk2: hex(p.primary), lt2: tint(p.primary, 0.9),
    accent1: accents[0], accent2: accents[1], accent3: accents[2], accent4: accents[3], accent5: accents[4], accent6: accents[5],
    hlink: hex(p.accent), folHlink: hex(p.muted),
  }
}

/** Series colours for charts: the kit's own list, then primary/accent/muted. */
export function seriesColors(kit) {
  const own = (kit.chart_style?.series_colors ?? []).map(hex)
  const more = [hex(kit.palette.primary), hex(kit.palette.accent), hex(kit.palette.muted), hex(kit.palette.positive), hex(kit.palette.warning)]
  return [...own, ...more.filter((c) => !own.includes(c))]
}
