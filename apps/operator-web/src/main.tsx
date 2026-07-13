import React from 'react'
import ReactDOM from 'react-dom/client'
import { SpaceBridgeShell, initTheme } from '@daypilot/ui-bridge'
import './styles.css'

// Apply the persisted theme (dark by default) before first paint so light
// users don't see a dark flash.
initTheme()

const emailEnabled = import.meta.env.VITE_DAYPILOT_EMAIL_ENABLED !== 'false'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SpaceBridgeShell emailEnabled={emailEnabled} />
  </React.StrictMode>,
)
