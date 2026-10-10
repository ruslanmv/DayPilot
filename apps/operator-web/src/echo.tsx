/**
 * `/echo` — the Echo Show display mode.
 *
 * A separate entry point, so the desktop console (`main.tsx`) is untouched and
 * the Echo downloads only what it renders: React, the shared sign-in gate and
 * the dashboard. Modules are imported by path rather than through the package
 * index for the same reason.
 */
import React from 'react'
import ReactDOM from 'react-dom/client'
import { AppGate } from '@daypilot/ui-bridge/src/auth/AppGate'
import { EchoDashboard } from '@daypilot/ui-bridge/src/echo/EchoDashboard'

import './echo.css'

// The Echo display is always dark. The desktop theme preference is neither read nor changed.
document.documentElement.setAttribute('data-theme', 'dark')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppGate>{(user, onSignOut) => <EchoDashboard user={user} onSignOut={onSignOut} />}</AppGate>
  </React.StrictMode>,
)
