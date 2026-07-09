import React from 'react'
import { StatusPill } from './StatusPill'

export function DashboardLayout({ children, compact = false }: { children: React.ReactNode; compact?: boolean }) {
  return (
    <main style={{ minHeight: '100vh', background: 'radial-gradient(circle at top, #102032, #05070d 55%)', padding: compact ? 16 : 32, color: '#eefbff' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'center', marginBottom: 24, flexWrap: 'wrap' }}>
        <div>
          <div style={{ color: '#00d9ff', letterSpacing: 3, fontSize: 12 }}>DAYPILOT ENTERPRISE</div>
          <h1 style={{ margin: '8px 0 0', fontSize: compact ? 28 : 44 }}>Space Bridge Operator Console</h1>
        </div>
        <StatusPill tone="ready">LOCAL-FIRST · GOVERNED · MCP</StatusPill>
      </header>
      {children}
    </main>
  )
}
