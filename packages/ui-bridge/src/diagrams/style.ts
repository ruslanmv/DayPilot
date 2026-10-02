/**
 * Markers and accent colours (batch B4). Both live in node metadata (`markers`, `accent`), so they
 * round-trip through every export and older readers simply keep them as unknown metadata.
 *
 * Accents tint a topic's outline and a thick edge bar; the label colour never changes, so text
 * contrast stays that of the theme. Each accent meets 3:1 against both the dark and light surface.
 */
export const MARKERS = [
  { id: 'flag', label: 'Flag', glyph: '⚑' },
  { id: 'star', label: 'Star', glyph: '★' },
  { id: 'check', label: 'Done', glyph: '✓' },
  { id: 'warning', label: 'Warning', glyph: '⚠' },
  { id: 'question', label: 'Question', glyph: '?' },
  { id: 'idea', label: 'Idea', glyph: '✦' },
  { id: 'priority-1', label: 'Priority 1', glyph: '①' },
  { id: 'priority-2', label: 'Priority 2', glyph: '②' },
  { id: 'priority-3', label: 'Priority 3', glyph: '③' },
  { id: 'clock', label: 'Waiting', glyph: '◷' },
  { id: 'lock', label: 'Locked', glyph: '⚿' },
] as const
export const MAX_MARKERS = 5

export const ACCENTS = [
  { id: 'indigo', label: 'Indigo', hex: '#6366f1' },
  { id: 'sky', label: 'Sky', hex: '#0284c7' },
  { id: 'teal', label: 'Teal', hex: '#0d9488' },
  { id: 'green', label: 'Green', hex: '#16a34a' },
  { id: 'amber', label: 'Amber', hex: '#d97706' },
  { id: 'red', label: 'Red', hex: '#dc2626' },
  { id: 'pink', label: 'Pink', hex: '#db2777' },
  { id: 'slate', label: 'Slate', hex: '#64748b' },
] as const

export const markerById = (id: unknown) => MARKERS.find((m) => m.id === id)
export const accentById = (id: unknown) => ACCENTS.find((a) => a.id === id)

/** Only known markers, no duplicates, at most MAX_MARKERS: whatever the file contained. */
export function cleanMarkers(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  for (const v of value) if (markerById(v) && !out.includes(v as string)) out.push(v as string)
  return out.slice(0, MAX_MARKERS)
}

/** "Flag, Star": for the accessible name of a topic. */
export function markerNames(value: unknown): string {
  return cleanMarkers(value)
    .map((id) => markerById(id)!.label)
    .join(', ')
}

/** WCAG 2.x contrast ratio between two #rrggbb colours. */
export function contrast(a: string, b: string): number {
  const lum = (hex: string) => {
    const [r, g, bl] = [1, 3, 5]
      .map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}
