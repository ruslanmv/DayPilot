import React from 'react'
import ReactDOM from 'react-dom/client'
import { SpaceBridgeShell } from '@daypilot/ui-bridge'
import './styles.css'

const emailEnabled = import.meta.env.VITE_DAYPILOT_EMAIL_ENABLED !== 'false'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SpaceBridgeShell emailEnabled={emailEnabled} />
  </React.StrictMode>,
)
