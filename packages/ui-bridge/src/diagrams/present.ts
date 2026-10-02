/**
 * Presenting a map (batch C5): the map becomes a title slide plus one slide per main branch, with
 * its sub-topics as bullets and any notes beneath. Pure and offline; text is data, rendered escaped.
 */
import type { Diagram } from './dmind'

export type Slide = { id: string; title: string; bullets: { text: string; level: number }[]; notes: string[]; branch: boolean }
export const MAX_SLIDES = 60
export const MAX_BULLETS = 24

export function toSlides(d: Diagram): Slide[] {
  const kind = d.kind === 'flowchart' ? 'flow' : 'branch'
  const byId = new Map(d.nodes.map((n) => [n.id, n]))
  const kids = new Map<string, string[]>()
  const hasParent = new Set<string>()
  for (const e of d.edges)
    if (e.kind === kind && byId.has(e.source) && byId.has(e.target) && !hasParent.has(e.target)) {
      kids.set(e.source, [...(kids.get(e.source) ?? []), e.target])
      hasParent.add(e.target)
    }
  const root = d.nodes.find((n) => !hasParent.has(n.id)) ?? d.nodes[0]
  const slides: Slide[] = [{ id: root.id, title: root.label, bullets: [], notes: root.notes ? [root.notes] : [], branch: false }]
  // A flowchart is one chain: present its steps as bullets of a single slide per ten steps.
  if (d.kind === 'flowchart') {
    const steps: string[] = []
    for (let id: string | undefined = (kids.get(root.id) ?? [])[0], guard = 0; id && guard < 1000; id = (kids.get(id) ?? [])[0], guard++) steps.push(id)
    for (let i = 0; i < steps.length && slides.length < MAX_SLIDES; i += 10) {
      slides.push({ id: steps[i], title: i ? `Steps ${i + 1}–${Math.min(i + 10, steps.length)}` : 'Steps', branch: true, notes: [], bullets: steps.slice(i, i + 10).map((s, k) => ({ text: `${i + k + 1}. ${byId.get(s)!.label}`, level: 0 })) })
    }
    return slides
  }
  for (const id of kids.get(root.id) ?? []) {
    if (slides.length >= MAX_SLIDES) break
    const n = byId.get(id)!
    const bullets: Slide['bullets'] = []
    const notes: string[] = n.notes ? [n.notes] : []
    const stack: [string, number][] = (kids.get(id) ?? []).slice().reverse().map((c) => [c, 0])
    while (stack.length && bullets.length < MAX_BULLETS) {
      const [cid, level] = stack.pop()!
      const c = byId.get(cid)!
      bullets.push({ text: c.label, level: Math.min(level, 3) })
      if (c.notes) notes.push(`${c.label}: ${c.notes}`)
      if (!c.collapsed) for (const g of (kids.get(cid) ?? []).slice().reverse()) stack.push([g, level + 1])
    }
    slides.push({ id, title: n.label, bullets, notes, branch: true })
  }
  return slides
}
