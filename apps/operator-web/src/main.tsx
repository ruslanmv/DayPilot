import React from 'react'
import ReactDOM from 'react-dom/client'
import { AppGate, SpaceBridgeShell, initTheme } from '@daypilot/ui-bridge'
import './styles.css'

// Apply the persisted theme (dark by default) before first paint so light
// users don't see a dark flash.
initTheme()

const emailEnabled = import.meta.env.VITE_DAYPILOT_EMAIL_ENABLED !== 'false'

// AppGate reads /v1/auth/config: it shows bootstrap/login when auth is enabled
// and the user isn't signed in, and the shell otherwise. In the local-first
// dev default (auth not required) the shell renders directly.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppGate>
      {(_user, onSignOut) => <SpaceBridgeShell emailEnabled={emailEnabled} onSignOut={onSignOut} />}
    </AppGate>
  </React.StrictMode>,
)
