import type { Pace, Slide, Storyline } from './client'

export const PACES: { id: Pace; label: string; wpm: number }[] = [
  { id: 'relaxed', label: 'Relaxed', wpm: 125 },
  { id: 'natural', label: 'Natural', wpm: 140 },
  { id: 'brisk', label: 'Brisk', wpm: 160 },
]
export const LENGTHS = [3, 5, 10, 15]

/** Slides that suit a talk of this length, including cover and closing (mirrors the server). */
export function suggestedSlides(minutes: number): number {
  for (const [limit, n] of [[3, 5], [5, 7], [8, 9], [10, 11], [15, 14], [20, 17], [30, 22]]) if (minutes <= limit) return n
  return Math.min(40, Math.round(minutes * 0.75))
}
export const countWords = (t?: string) => (t ?? '').trim().split(/\s+/).filter(Boolean).length
export const clock = (sec: number) => `${Math.floor(sec / 60)}:${String(Math.round(sec % 60)).padStart(2, '0')}`
export const wpmOf = (s: Storyline) => s.talk?.wpm ?? 140
/** Words this slide's time allows at the talk's pace. */
export const budget = (slide: Slide, wpm: number) => Math.round(((slide.seconds ?? 0) * wpm) / 60)
export function fit(words: number, target: number): 'ok' | 'short' | 'long' | 'missing' {
  if (!words) return 'missing'
  if (words < target * 0.6) return 'short'
  if (words > target * 1.25) return 'long'
  return 'ok'
}
export const hasScript = (s?: Storyline | null) => !!s?.slides.some((x) => (x.script ?? '').trim())
