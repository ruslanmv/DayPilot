import React from 'react'
import { apiBase } from '../env'
import { portraitUrl } from './portraitUrl'

/**
 * An agent's portrait, with initials as the fallback.
 *
 * The fallback has to survive two different failures, and the directory used to
 * survive neither:
 *
 *  - **no portrait at all** — `avatarUrl` is null because the persona has no
 *    committed appearance. Handled by every call site already.
 *  - **a portrait that fails to load** — the proxy 404s, HomePilot is down, the
 *    file was deleted. The old code hid the broken `<img>` and rendered nothing
 *    in its place, leaving an empty grey circle with no clue whose it was.
 *
 * Both now land on the same initials, so an agent is always identifiable.
 * Rendering it once here also keeps the card, the workspace header and the chat
 * bubbles from drifting into three different fallbacks.
 */
export function agentInitials(name: string, max = 2): string {
  const parts = (name || '').trim().split(/\s+/).slice(0, max)
  return parts.map((p) => p[0]?.toUpperCase() || '').join('') || 'A'
}

export function AgentPortrait({
  name,
  avatarUrl,
  className,
  initialsClassName = 'dp-agentcard__initials',
  maxInitials = 2,
  as: Tag = 'div',
}: {
  name: string
  avatarUrl?: string | null
  className?: string
  initialsClassName?: string
  maxInitials?: number
  as?: 'div' | 'span'
}) {
  const [failed, setFailed] = React.useState(false)

  // A new URL deserves a new attempt — otherwise re-syncing an agent whose
  // portrait is now fine would keep showing initials until a full reload.
  React.useEffect(() => { setFailed(false) }, [avatarUrl])

  const showImage = Boolean(avatarUrl) && !failed

  return (
    <Tag className={className} aria-hidden="true">
      {showImage
        ? (
          <img
            src={portraitUrl(avatarUrl, apiBase())}
            alt=""
            loading="lazy"
            onError={() => setFailed(true)}
          />
          )
        : <span className={initialsClassName}>{agentInitials(name, maxInitials)}</span>}
    </Tag>
  )
}
