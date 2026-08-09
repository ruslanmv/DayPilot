import React from 'react'
import ReactDOM from 'react-dom/client'
import { AppGate, SpaceBridgeShell, initTheme } from '@daypilot/ui-bridge'
import './styles.css'

// Apply the persisted theme (dark by default) before first paint so light
// users don't see a dark flash.
initTheme()

const emailEnabled = import.meta.env.VITE_DAYPILOT_EMAIL_ENABLED !== 'false'
// The Slack communication workspace is opt-in on both sides: this flag adds the
// tab, and DAYPILOT_SLACK_WORKSPACE_ENABLED on the API serves it. A tab whose
// routes 404 is worse than no tab, so neither flag alone turns it on.
const slackEnabled = import.meta.env.VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED === 'true'

// AppGate reads /v1/auth/config: it shows bootstrap/login when auth is enabled
// and the user isn't signed in, and the shell otherwise. In the local-first
// dev default (auth not required) the shell renders directly.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppGate>
      {(user, onSignOut) => <SpaceBridgeShell emailEnabled={emailEnabled} slackEnabled={slackEnabled} onSignOut={onSignOut} user={user} />}
    </AppGate>
  </React.StrictMode>,
)
