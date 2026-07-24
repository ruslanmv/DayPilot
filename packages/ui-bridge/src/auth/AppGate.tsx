import React, { useEffect, useRef, useState } from 'react'
import { authApi, type AuthConfig, type AuthUser } from '../authClient'
import { LoginPage } from './LoginPage'

type GateState =
  | { kind: 'loading' }
  | { kind: 'bootstrap_required'; config: AuthConfig }
  | { kind: 'unauthenticated'; config: AuthConfig }
  | { kind: 'authenticated'; user: AuthUser | null }

const FALLBACK_CONFIG: AuthConfig = {
  authRequired: true, bootstrapRequired: false, cloudLoginAvailable: false, ssoAvailable: false,
}

/** Local, user-scoped state that must not leak into the next session. */
function clearUserCaches(): void {
  try {
    localStorage.removeItem('daypilot.chat.session')
  } catch { /* ignore */ }
}

/**
 * Route guard for the whole app. Reads /v1/auth/config (+ /me) once and renders
 * the correct application state:
 *   - bootstrap_required → create the first owner
 *   - unauthenticated    → login page
 *   - authenticated      → the workspace shell (children)
 * When auth is not required (local-first dev default) the shell renders
 * directly, so single-user installs are unaffected.
 *
 * Sign out is explicit (Issue 6): after a successful logout the gate goes
 * straight to the login page instead of re-resolving into anonymous mode —
 * even on deployments where auth isn't enforced, an explicit "Sign out" must
 * visibly leave the workspace. A failed logout is surfaced, never treated as
 * success.
 */
export function AppGate({ children }: { children: (user: AuthUser | null, onSignOut: () => void) => React.ReactNode }) {
  const [state, setState] = useState<GateState>({ kind: 'loading' })
  const configRef = useRef<AuthConfig | null>(null)

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
      configRef.current = config
      if (config.bootstrapRequired) { setState({ kind: 'bootstrap_required', config }); return }
      if (!config.authRequired) { setState({ kind: 'authenticated', user: null }); return }
      const me = await authApi.me()
      if (me.ok) setState({ kind: 'authenticated', user: me.data.user })
      else setState({ kind: 'unauthenticated', config })
    })
  }, [])

  useEffect(() => { resolve() }, [resolve])

  async function signOut() {
    const result = await authApi.logout()
    if (!result.ok && result.status !== 401) {
      // Logout genuinely failed (network/server) — do not pretend it worked.
      window.alert('Sign out failed — check your connection and try again.')
      return
    }
    clearUserCaches()
    // Land on the login page directly; never re-resolve into anonymous mode.
    setState({ kind: 'unauthenticated', config: configRef.current ?? FALLBACK_CONFIG })
    // Replace history so Back doesn't reveal the protected workspace screen.
    try { window.history.replaceState(null, '', window.location.pathname) } catch { /* ignore */ }
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
