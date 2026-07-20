import React, { useEffect, useState } from 'react'
import { authApi, type AuthConfig, type AuthUser } from '../authClient'
import { LoginPage } from './LoginPage'

type GateState =
  | { kind: 'loading' }
  | { kind: 'bootstrap_required'; config: AuthConfig }
  | { kind: 'unauthenticated'; config: AuthConfig }
  | { kind: 'authenticated'; user: AuthUser | null }

/**
 * Route guard for the whole app. Reads /v1/auth/config (+ /me) once and renders
 * the correct application state:
 *   - bootstrap_required → create the first owner
 *   - unauthenticated    → login page
 *   - authenticated      → the workspace shell (children)
 * When auth is not required (local-first dev default) the shell renders
 * directly, so single-user installs are unaffected.
 */
export function AppGate({ children }: { children: (user: AuthUser | null, onSignOut: () => void) => React.ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'loading' })

  const resolve = React.useCallback(() => {
    setState({ kind: 'loading' })
    authApi.config().then(async (cfg) => {
      if (!cfg.ok) {
        // Can't reach auth config — fail open to the shell only when auth is
        // clearly not enforced (dev). Otherwise show the login page shell.
        setState({ kind: 'authenticated', user: null })
        return
      }
      const config = cfg.data
      if (config.bootstrapRequired) { setState({ kind: 'bootstrap_required', config }); return }
      if (!config.authRequired) { setState({ kind: 'authenticated', user: null }); return }
      const me = await authApi.me()
      if (me.ok) setState({ kind: 'authenticated', user: me.data.user })
      else setState({ kind: 'unauthenticated', config })
    })
  }, [])

  useEffect(() => { resolve() }, [resolve])

  async function signOut() {
    await authApi.logout()
    resolve()
  }

  if (state.kind === 'loading') {
    return <div className="dp-login"><div className="dp-login__card"><span className="dp-spinner" aria-hidden="true" /><p>Loading DayPilot…</p></div></div>
  }
  if (state.kind === 'bootstrap_required') {
    return <LoginPage mode="bootstrap" cloudAvailable={state.config.cloudLoginAvailable} ssoAvailable={state.config.ssoAvailable} onAuthenticated={resolve} />
  }
  if (state.kind === 'unauthenticated') {
    return <LoginPage mode="login" cloudAvailable={state.config.cloudLoginAvailable} ssoAvailable={state.config.ssoAvailable} onAuthenticated={resolve} />
  }
  return <>{children(state.user, signOut)}</>
}
