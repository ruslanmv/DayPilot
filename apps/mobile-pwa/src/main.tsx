import React from 'react'
import ReactDOM from 'react-dom/client'
import { MobileShell } from '@daypilot/ui-bridge'
import './styles.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <MobileShell />
  </React.StrictMode>,
)

// Register the service worker for offline launch + push-ready approvals.
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').then((registration) => {
      // Update flow: when a new SW is installed, activate it on next load.
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing
        if (worker) {
          worker.addEventListener('statechange', () => {
            if (worker.state === 'installed' && navigator.serviceWorker.controller) {
              worker.postMessage('skipWaiting')
            }
          })
        }
      })
    }).catch(() => {
      /* offline or unsupported — app still works from cache */
    })
  })
}
