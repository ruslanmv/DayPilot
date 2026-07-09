import React from 'react'

export function Card({ title, eyebrow, children, footer }: {
  title: string
  eyebrow?: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <article style={{ minHeight: 140, border: '1px solid rgba(111, 226, 255, .24)', borderRadius: 18, background: 'rgba(6, 14, 24, .72)', padding: 18, boxShadow: '0 0 32px rgba(0,217,255,.06)' }}>
      {eyebrow ? <div style={{ color: '#ffcc66', fontSize: 11, letterSpacing: 1.8, marginBottom: 8 }}>{eyebrow}</div> : null}
      <h2 style={{ margin: 0, color: '#d8f7ff', fontSize: 18 }}>{title}</h2>
      <div style={{ color: '#8eb7c2', lineHeight: 1.5 }}>{children}</div>
      {footer ? <div style={{ marginTop: 16 }}>{footer}</div> : null}
    </article>
  )
}
