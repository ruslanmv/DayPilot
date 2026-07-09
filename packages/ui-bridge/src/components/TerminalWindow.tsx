import React from 'react'

export function TerminalWindow({ title = 'Trace Console', lines }: { title?: string; lines: string[] }) {
  return (
    <section style={{ border: '1px solid rgba(111,226,255,.20)', borderRadius: 18, overflow: 'hidden', background: '#05070d' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', padding: '10px 14px', borderBottom: '1px solid rgba(111,226,255,.16)', color: '#d8f7ff' }}>
        <strong>{title}</strong>
        <span style={{ color: '#8eb7c2' }}>live</span>
      </header>
      <pre style={{ margin: 0, padding: 16, minHeight: 160, color: '#9ff4ff', whiteSpace: 'pre-wrap', fontSize: 13 }}>
        {lines.map((line, index) => `#${String(index + 1).padStart(2, '0')} ${line}`).join('\n')}
      </pre>
    </section>
  )
}
