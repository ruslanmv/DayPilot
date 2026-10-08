import React from 'react'
import { dateOf, type Gantt } from './tasks'

const ROW = 30
const LEFT = 190
const COLORS = { todo: '#6b7a99', doing: '#4f8cff', done: '#2fa66a' } as const

/** A simple, readable Gantt chart as SVG, with the same data as an accessible table. */
export function GanttView({ data }: { data: Gantt }) {
  if (!data.rows.length) return <p>No scheduled tasks yet. Choose a start date and press Schedule.</p>
  const days = Math.max(1, data.last - data.first)
  const px = Math.max(6, Math.min(40, Math.floor(760 / days)))
  const width = LEFT + days * px + 20
  const height = 34 + data.rows.length * ROW
  const x = (d: number) => LEFT + (d - data.first) * px
  const y = (i: number) => 34 + i * ROW
  const index = new Map(data.rows.map((r, i) => [r.id, i]))
  const step = days > 120 ? 28 : 7
  const ticks: number[] = []
  for (let d = data.first; d <= data.last; d += step) ticks.push(d)
  return (
    <div className="dmind-gantt">
      <svg role="img" aria-label={`Gantt chart of ${data.rows.length} tasks from ${dateOf(data.first)} to ${dateOf(data.last - 1)}`} width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {ticks.map((d) => (
          <g key={d}>
            <line x1={x(d)} x2={x(d)} y1={22} y2={height} stroke="currentColor" opacity={0.15} />
            <text x={x(d) + 3} y={16} fontSize={11} fill="currentColor" opacity={0.7}>
              {dateOf(d).slice(5)}
            </text>
          </g>
        ))}
        {data.rows.map((r, i) => (
          <g key={r.id}>
            <text x={6} y={y(i) + 19} fontSize={12} fill="currentColor">
              {r.label.length > 26 ? r.label.slice(0, 25) + '…' : r.label}
            </text>
            <rect x={x(r.start)} y={y(i) + 5} width={Math.max(4, (r.end - r.start) * px - 2)} height={ROW - 12} rx={4} fill={COLORS[r.status]} opacity={r.status === 'done' ? 0.6 : 1} />
            {r.waitsFor.map((p) => {
              const j = index.get(p)
              if (j === undefined) return null
              const from = data.rows[j]
              return <path key={p} d={`M${x(from.end) - 2},${y(j) + ROW / 2} H${x(from.end) + 4} V${y(i) + ROW / 2} H${x(r.start)}`} fill="none" stroke="currentColor" opacity={0.45} />
            })}
          </g>
        ))}
      </svg>
      <table className="dmind-sr-only">
        <caption>Task schedule</caption>
        <thead>
          <tr>
            <th>Task</th>
            <th>Start</th>
            <th>End</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r) => (
            <tr key={r.id}>
              <td>{r.label}</td>
              <td>{dateOf(r.start)}</td>
              <td>{dateOf(r.end - 1)}</td>
              <td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
