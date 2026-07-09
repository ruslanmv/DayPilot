import React from 'react'
import { Button } from './Button'
import { StatusPill } from './StatusPill'

export type ApprovalItem = {
  id: string
  title: string
  risk: 'low' | 'medium' | 'high'
  tool: string
  reason: string
}

export function ApprovalQueue({ items = [] }: { items?: ApprovalItem[] }) {
  const queue = items.length ? items : [{ id: 'sample', title: 'HomePilot persona import', risk: 'medium' as const, tool: 'homepilot.import_hpersona', reason: 'Write-capable persona dependencies require review.' }]
  return (
    <div style={{ display: 'grid', gap: 12 }}>
      {queue.map(item => (
        <div key={item.id} style={{ border: '1px solid rgba(111,226,255,.18)', borderRadius: 14, padding: 14, background: 'rgba(255,255,255,.03)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
            <strong style={{ color: '#d8f7ff' }}>{item.title}</strong>
            <StatusPill tone={item.risk === 'high' ? 'blocked' : item.risk === 'medium' ? 'warning' : 'ready'}>{item.risk}</StatusPill>
          </div>
          <p style={{ color: '#8eb7c2', margin: '8px 0' }}>{item.reason}</p>
          <code style={{ color: '#9ff4ff' }}>{item.tool}</code>
          <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
            <Button variant="primary">Approve</Button>
            <Button variant="danger">Block</Button>
          </div>
        </div>
      ))}
    </div>
  )
}
