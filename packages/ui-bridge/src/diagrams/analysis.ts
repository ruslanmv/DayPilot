/**
 * Deterministic graph analysis (batch B6). Everything here is computed from the document alone and
 * labelled `origin: 'solver'`, so it is never confused with a model suggestion. Iterative, bounded
 * by the 1000-node / 4000-edge contract limits.
 */
import type { Diagram, DiagramEdge } from './dmind'

export type Finding = {
  origin: 'solver'
  code: 'unreachable' | 'dead_end' | 'cycle' | 'no_exit' | 'orphan'
  severity: 'info' | 'warning'
  nodes: string[]
  message: string
}
export type Analysis = {
  origin: 'solver'
  /** Flow/dependency order, dependencies first; null when a cycle prevents one. */
  order: string[] | null
  components: string[][]
  findings: Finding[]
}

/** Links that carry execution/dependency direction; `branch` is hierarchy, `relationship` is loose. */
const directed = (e: DiagramEdge) => e.kind === 'flow' || e.kind === 'dependency'

export function analyse(d: Diagram): Analysis {
  const ids = d.nodes.map((n) => n.id)
  const label = new Map(d.nodes.map((n) => [n.id, n.label]))
  const out = new Map<string, string[]>(ids.map((i) => [i, []]))
  const inn = new Map<string, number>(ids.map((i) => [i, 0]))
  for (const e of d.edges) {
    if (!directed(e) || !out.has(e.source) || !out.has(e.target)) continue
    out.get(e.source)!.push(e.target)
    inn.set(e.target, inn.get(e.target)! + 1)
  }
  const findings: Finding[] = []
  const name = (list: string[]) => list.map((i) => `"${label.get(i)}"`).join(', ')

  // Strongly connected components, iterative Tarjan.
  const index = new Map<string, number>()
  const low = new Map<string, number>()
  const onStack = new Set<string>()
  const stack: string[] = []
  const components: string[][] = []
  let counter = 0
  for (const root of ids) {
    if (index.has(root)) continue
    const work: [string, number][] = [[root, 0]]
    index.set(root, counter)
    low.set(root, counter++)
    stack.push(root)
    onStack.add(root)
    while (work.length) {
      const frame = work[work.length - 1]
      const [v, i] = frame
      const next = out.get(v)!
      if (i < next.length) {
        frame[1]++
        const w = next[i]
        if (!index.has(w)) {
          index.set(w, counter)
          low.set(w, counter++)
          stack.push(w)
          onStack.add(w)
          work.push([w, 0])
        } else if (onStack.has(w)) low.set(v, Math.min(low.get(v)!, index.get(w)!))
      } else {
        work.pop()
        if (work.length) {
          const p = work[work.length - 1][0]
          low.set(p, Math.min(low.get(p)!, low.get(v)!))
        }
        if (low.get(v) === index.get(v)) {
          const comp: string[] = []
          let w: string
          do {
            w = stack.pop()!
            onStack.delete(w)
            comp.push(w)
          } while (w !== v)
          components.push(comp.sort())
        }
      }
    }
  }
  const loops = components.filter((c) => c.length > 1 || out.get(c[0])!.includes(c[0]))
  const inLoop = new Set(loops.flat())
  for (const c of loops) {
    findings.push({ origin: 'solver', code: 'cycle', severity: 'info', nodes: c, message: `Loop through ${name(c)}.` })
    const members = new Set(c)
    const exits = c.some((v) => out.get(v)!.some((t) => !members.has(t)))
    if (!exits)
      findings.push({
        origin: 'solver',
        code: 'no_exit',
        severity: 'warning',
        nodes: c,
        message: `Nothing leaves the loop through ${name(c)}; it can never finish.`,
      })
  }

  // Dependency order (Kahn) ignoring nothing: null if any loop exists.
  let order: string[] | null = null
  if (!loops.length) {
    const left = new Map(inn)
    const queue = ids.filter((i) => left.get(i) === 0)
    const done: string[] = []
    while (queue.length) {
      const v = queue.shift()!
      done.push(v)
      for (const t of out.get(v)!) {
        left.set(t, left.get(t)! - 1)
        if (left.get(t) === 0) queue.push(t)
      }
    }
    order = done
  }

  if (d.kind === 'flowchart') {
    // A start is a step nothing leads into, or any member of a loop that nothing outside leads into.
    const comp = new Map<string, number>()
    components.forEach((c, k) => c.forEach((v) => comp.set(v, k)))
    const fed = new Set<number>()
    for (const [v, targets] of out) for (const t of targets) if (comp.get(v) !== comp.get(t)) fed.add(comp.get(t)!)
    const starts = ids.filter((i) => out.get(i)!.length && !fed.has(comp.get(i)!))
    const seen = new Set<string>()
    const todo = [...starts]
    while (todo.length) {
      const v = todo.pop()!
      if (seen.has(v)) continue
      seen.add(v)
      todo.push(...out.get(v)!)
    }
    const unreachable = ids.filter((i) => !seen.has(i) && (inn.get(i)! > 0 || out.get(i)!.length > 0) && !inLoop.has(i))
    if (unreachable.length)
      findings.push({ origin: 'solver', code: 'unreachable', severity: 'warning', nodes: unreachable, message: `Not reachable from any start: ${name(unreachable)}.` })
    const dead = ids.filter((i) => inn.get(i)! > 0 && out.get(i)!.length === 0)
    if (dead.length > 1)
      findings.push({ origin: 'solver', code: 'dead_end', severity: 'info', nodes: dead, message: `Steps with no next step: ${name(dead)}.` })
  }
  const linked = new Set<string>()
  d.edges.forEach((e) => (linked.add(e.source), linked.add(e.target)))
  const orphans = ids.filter((i) => !linked.has(i))
  if (orphans.length && d.nodes.length > 1)
    findings.push({ origin: 'solver', code: 'orphan', severity: 'warning', nodes: orphans, message: `Not connected to anything: ${name(orphans)}.` })
  return { origin: 'solver', order, components: components.sort((a, b) => a[0].localeCompare(b[0])), findings }
}
