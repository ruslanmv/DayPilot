import React from 'react'
import ReactDOM from 'react-dom/client'
import { SpaceBridgeShell } from '@daypilot/ui-bridge'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <SpaceBridgeShell compact />
  </React.StrictMode>,
)
