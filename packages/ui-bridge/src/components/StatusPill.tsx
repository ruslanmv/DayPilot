import React from 'react'

export type StatusTone = 'ready' | 'warning' | 'blocked' | 'neutral'

const toneStyle: Record<StatusTone, React.CSSProperties> = {
  ready: { color: '#9ff4ff', borderColor: 'rgba(0,217,255,.45)' },
  warning: { color: '#ffdf93', borderColor: 'rgba(255,204,102,.55)' },
  blocked: { color: '#ffd4db', borderColor: 'rgba(255,98,121,.60)' },
  neutral: { color: '#b9d7df', borderColor: 'rgba(142,183,194,.35)' },
}

export function StatusPill({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: StatusTone }) {
  return (
    <span style={{ border: '1px solid', borderRadius: 999, padding: '7px 11px', fontSize: 12, fontWeight: 700, ...toneStyle[tone] }}>
      {children}
    </span>
  )
}
