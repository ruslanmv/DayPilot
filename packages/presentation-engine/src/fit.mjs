/**
 * Text measurement and fitting from real advance widths (see metrics/fonts.json). Used both to
 * choose a font size within a role's limits and, later, to prove a text box does not overflow.
 * Fonts without metrics are measured conservatively and reported as unverified.
 */
import { createRequire } from 'node:module'

const METRICS = createRequire(import.meta.url)('./metrics/fonts.json')
// Single-spaced line height relative to the em, per family (ascent + descent + gap, rounded up).
const LINE = { Arial: 1.15, 'Times New Roman': 1.15, 'Courier New': 1.14, Calibri: 1.22, Cambria: 1.18 }
const FALLBACK_EM = 0.6

export const hasMetrics = (font) => Object.prototype.hasOwnProperty.call(METRICS, font)
export const lineFactor = (font) => LINE[font] ?? 1.25

/** Width in inches of `text` at `pt` points. */
export function measure(text, font, pt, bold = false) {
  const table = METRICS[font]?.[bold ? 'bold' : 'regular']
  let units = 0
  for (const ch of text) {
    const w = table?.[ch.codePointAt(0)]
    units += w ?? (ch === ' ' ? 280 : FALLBACK_EM * 1000 * (bold ? 1.06 : 1))
  }
  return (units / 1000) * (pt / 72)
}

/** Greedy word wrap; words longer than the line are broken by characters. */
export function wrap(text, width, font, pt, bold = false) {
  const lines = []
  for (const para of String(text).split('\n')) {
    const words = para.split(/\s+/).filter(Boolean)
    if (!words.length) {
      lines.push('')
      continue
    }
    let line = ''
    for (let word of words) {
      const candidate = line ? line + ' ' + word : word
      if (measure(candidate, font, pt, bold) <= width) {
        line = candidate
        continue
      }
      if (line) lines.push(line)
      line = ''
      while (measure(word, font, pt, bold) > width) {
        let cut = word.length - 1
        while (cut > 1 && measure(word.slice(0, cut), font, pt, bold) > width) cut--
        lines.push(word.slice(0, cut))
        word = word.slice(cut)
      }
      line = word
    }
    lines.push(line)
  }
  return lines
}

/**
 * Largest size in [minPt, maxPt] at which the paragraphs fit the box. `indent` (inches) is
 * removed from the width of every line (bullets); `paraGapPt` is added after each paragraph.
 */
export function fit(text, box, { font, bold = false, maxPt, minPt, indent = 0, paraGapPt = 0, lineSpacing = 1 }) {
  const paras = String(text).split('\n').length
  for (let pt = maxPt; pt >= minPt; pt--) {
    const lines = wrap(text, Math.max(0.1, box.w - indent), font, pt, bold)
    const height = (lines.length * pt * lineFactor(font) * lineSpacing + Math.max(0, paras - 1) * paraGapPt) / 72
    if (height <= box.h) return { pt, lines: lines.length, height, fits: true, verified: hasMetrics(font) }
  }
  const lines = wrap(text, Math.max(0.1, box.w - indent), font, minPt, bold)
  const height = (lines.length * minPt * lineFactor(font) * lineSpacing + Math.max(0, paras - 1) * paraGapPt) / 72
  return { pt: minPt, lines: lines.length, height, fits: false, verified: hasMetrics(font) }
}
