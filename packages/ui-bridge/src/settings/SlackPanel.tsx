import React from 'react'

import { explain, slackApi } from '../slack/slackClient'
import type {
  SlackContextSource,
  SlackPreferences,
  SlackSettingsPayload,
  SlackStatus,
} from '../slack/slackTypes'

/**
 * Settings → Slack.
 *
 * Five sections, in the order someone actually asks the questions: what is
 * connected, when should it draft, **what may it read**, what must it never
 * repeat, and how loudly should it tell me.
 *
 * Two deliberate absences:
 *
 * * There is no "send automatically" switch. Never auto-sending is an invariant
 *   of the service — the server has no column for it — so it renders here as a
 *   locked policy line. A disabled toggle would still imply the setting exists;
 *   a statement does not.
 * * There is no way to widen the AI's reach beyond the context list. That list
 *   is a permission, served by the API, and a source whose integration is not
 *   connected renders unavailable rather than pretending otherwise.
 */

function Toggle({ on, onChange, label, id, disabled = false }: {
  on: boolean; onChange: (v: boolean) => void; label: string; id: string; disabled?: boolean
}) {
  return (
    <button
      type="button" id={id} role="switch" aria-checked={on} aria-label={label} disabled={disabled}
      className={'dp-switch' + (on ? ' is-on' : '')}
      onClick={() => onChange(!on)}
    >
      <span className="dp-switch__knob" aria-hidden="true" />
    </button>
  )
}

function Hint({ text }: { text: string }) {
  return <span className="dp-cset__hint" title={text} aria-label={text} role="img">ⓘ</span>
}

export function SlackPanel() {
  const [payload, setPayload] = React.useState<SlackSettingsPayload | null>(null)
  const [status, setStatus] = React.useState<SlackStatus | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [disabled, setDisabled] = React.useState(false)

  const load = React.useCallback(async () => {
    const st = await slackApi.status()
    if (st.ok) {
      setStatus(st.data)
      if (!st.data.enabled) { setDisabled(true); return }
    }
    const s = await slackApi.settings()
    if (s.ok) { setPayload(s.data); setError(null) } else setError(explain(s.error, s.status))
  }, [])

  React.useEffect(() => { void load() }, [load])

  // Optimistic, then reconciled — a toggle that waits for a round trip feels
  // broken, but the server's answer is what ends up on screen.
  const save = React.useCallback(async (patch: Partial<SlackPreferences>) => {
    setPayload((cur) => (cur ? { ...cur, settings: { ...cur.settings, ...patch } } : cur))
    const r = await slackApi.saveSettings(patch)
    if (!r.ok) { setError(explain(r.error, r.status)); void load(); return }
    setError(null)
    setPayload((cur) => (cur ? { ...cur, settings: r.data } : cur))
  }, [load])

  if (disabled) {
    return (
      <div className="dp-cset">
        <p className="dp-cset__lede">
          The Slack workspace is not enabled on this deployment. Set
          <code> DAYPILOT_SLACK_WORKSPACE_ENABLED=1 </code> on the API and
          <code> VITE_DAYPILOT_SLACK_WORKSPACE_ENABLED=true </code> in the web app to turn it on.
          DayPilot works fully without it.
        </p>
      </div>
    )
  }
  if (error && !payload) {
    return <p className="dp-standupcard__error" role="alert">Couldn’t load Slack settings: {error}</p>
  }
  if (!payload) return <p className="dp-home__card-empty">Loading Slack settings…</p>

  const s = payload.settings
  const connected = Boolean(status?.connected)

  const toggleSource = (id: string, on: boolean) => {
    const next = on
      ? [...new Set([...s.contextSources, id])]
      : s.contextSources.filter((x) => x !== id)
    void save({ contextSources: next })
  }

  return (
    <div className="dp-cset">
      {error && <p className="dp-standupcard__error" role="alert">{error}</p>}

      {/* 1 — connection --------------------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="slk-connection">
        <h5 className="dp-cset__title" id="slk-connection">1. Slack connection</h5>
        <div className="dp-cset__cards">
          <div className={'dp-cset__conn' + (connected ? '' : ' dp-cset__conn--empty')}>
            <span className="dp-cset__mark" aria-hidden="true">#</span>
            <div className="dp-cset__conn-body">
              <div className="dp-cset__conn-head">
                <strong>Slack</strong>
                {connected
                  ? <span className="dp-cset__ok">Connected ✓</span>
                  : <span className="dp-cset__muted">Not connected</span>}
              </div>
              <div className="dp-cset__conn-meta">
                {[status?.account, status?.capabilities?.join(' · ')].filter(Boolean).join(' · ')
                  || 'DayPilot reads the conversations you choose and drafts replies. It posts nothing without your approval.'}
              </div>
            </div>
          </div>
        </div>

        <div className="dp-cset__field">
          <span>Access mode</span>
          <Hint text="Standard uses the Slack app's bot connection: channels it is in, and messages that mention it. Personal messages need your own Slack authorization — the bot connection cannot read your DMs, and DayPilot will not pretend it can." />
          <select
            className="dp-cset__select"
            aria-label="Slack access mode"
            value={s.accessMode}
            onChange={(e) => void save({ accessMode: e.target.value as SlackPreferences['accessMode'] })}
          >
            <option value="standard">Standard — channels and mentions (bot connection)</option>
            <option value="personal">Personal — includes your direct messages (you authorize)</option>
          </select>
        </div>
        {s.accessMode === 'personal' && !status?.personalMessagesAvailable && (
          <p className="dp-cset__note">
            Personal access needs a separate, user-level Slack authorization. Until that is
            granted, DayPilot will keep working with channels and mentions only.
          </p>
        )}
        {status?.delivery && (
          <p className="dp-cset__note">
            Events arrive over {status.delivery.transport === 'socket'
              ? 'Socket Mode — no public URL required, which is why it is the default for a local-first install.'
              : `an HTTPS request URL (${status.delivery.eventsPath}). This deployment must be reachable from Slack.`}
            {status.delivery.transport === 'http' && !status.delivery.signingSecretConfigured
              && ' A signing secret is not configured yet, so inbound events are refused.'}
          </p>
        )}
      </section>

      {/* 2 — drafting ------------------------------------------------------ */}
      <section className="dp-cset__section" aria-labelledby="slk-drafting">
        <h5 className="dp-cset__title" id="slk-drafting">2. AI drafting</h5>
        <p className="dp-cset__lede">
          DayPilot does not draft a reply to everything. It reads each message, decides whether
          it needs you, and only prepares something when it does — a “thanks 👍” is shown and
          left alone.
        </p>
        <div className="dp-cset__row">
          <Toggle id="slk-auto" on={s.autoPrepare} label="Prepare drafts automatically"
                  onChange={(v) => void save({ autoPrepare: v })} />
          <label htmlFor="slk-auto">Prepare drafts automatically</label>
          <Hint text="Off means nothing is drafted until you ask. The inbox still tells you which conversations need a reply." />
        </div>
        <div className="dp-cset__row">
          <Toggle id="slk-dm" on={s.draftDirectMessages} label="Draft replies to direct messages"
                  onChange={(v) => void save({ draftDirectMessages: v })} />
          <label htmlFor="slk-dm">Direct messages</label>
        </div>
        <div className="dp-cset__row">
          <Toggle id="slk-mention" on={s.draftMentions} label="Draft replies when you are mentioned"
                  onChange={(v) => void save({ draftMentions: v })} />
          <label htmlFor="slk-mention">Mentions of you</label>
        </div>
        <div className="dp-cset__row">
          <Toggle id="slk-threads" on={s.draftParticipatingThreads} label="Draft replies in threads you are part of"
                  onChange={(v) => void save({ draftParticipatingThreads: v })} />
          <label htmlFor="slk-threads">Threads you are already in</label>
        </div>
        <div className="dp-cset__row">
          <Toggle id="slk-all" on={s.draftAllChannelMessages} label="Draft replies to every channel message"
                  onChange={(v) => void save({ draftAllChannelMessages: v })} />
          <label htmlFor="slk-all">Every message in channels you are in</label>
          <Hint text="Usually more noise than help — a busy channel produces drafts for conversations that were never addressed to you." />
        </div>
      </section>

      {/* 3 — context (the allow-list) -------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="slk-context">
        <h5 className="dp-cset__title" id="slk-context">3. Context available to Slack AI</h5>
        <p className="dp-cset__lede">
          Choose what a Slack draft may read. Nothing outside this list is gathered, and every
          draft names the sources behind it.
        </p>
        <div className="dp-cset__sources">
          {payload.sources.map((src: SlackContextSource) => {
            const checked = src.alwaysOn || s.contextSources.includes(src.id)
            return (
              <label
                key={src.id}
                className={'dp-cset__source' + (src.available ? '' : ' is-unavailable')}
                title={src.available ? undefined : `${src.label} — not connected`}
              >
                <input
                  type="checkbox"
                  checked={checked && src.available}
                  disabled={!src.available || src.alwaysOn}
                  onChange={(e) => toggleSource(src.id, e.target.checked)}
                />
                <span className="dp-cset__source-label">{src.label}</span>
                {!src.available && <span className="dp-cset__muted">Not connected</span>}
              </label>
            )
          })}
        </div>
        <div className="dp-cset__row">
          <Toggle id="slk-history" on={s.usePreviousConversations} label="Use previous messages in the conversation"
                  onChange={(v) => void save({ usePreviousConversations: v })} />
          <label htmlFor="slk-history">Use earlier messages in the same conversation</label>
          <Hint text="Recent history from this conversation only — not your whole Slack workspace." />
        </div>
      </section>

      {/* 4 — privacy -------------------------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="slk-privacy">
        <h5 className="dp-cset__title" id="slk-privacy">4. Privacy &amp; recipient protection</h5>
        <p className="dp-cset__lede">
          What DayPilot may <em>read</em> and what a recipient may <em>hear</em> are different
          questions. An internal note can stop a draft over-promising without ever appearing in
          the message.
        </p>
        <div className="dp-cset__row">
          <Toggle id="slk-protect" on={s.recipientProtection} label="Never reveal internal context to external recipients"
                  onChange={(v) => void save({ recipientProtection: v })} />
          <label htmlFor="slk-protect">Never reveal internal context to external recipients</label>
          <Hint text="Internal facts are removed before the draft is written, not asked to be kept quiet afterwards — so no prompt, and no instruction hidden in an incoming message, can surface them." />
        </div>

        <div className="dp-cset__row dp-cset__row--locked">
          <span className="dp-cset__lock" aria-hidden="true">🔒</span>
          <span className="dp-cset__locked-label">Never automatically send a Slack message</span>
          <span className="dp-cset__ok">Always on</span>
        </div>
        <p className="dp-cset__note">
          That last line is not a switch. Sending goes through the Approval Center, and there is
          no setting — and no column in the database — that could turn it off.
        </p>
      </section>

      {/* 5 — notifications --------------------------------------------------- */}
      <section className="dp-cset__section" aria-labelledby="slk-notify">
        <h5 className="dp-cset__title" id="slk-notify">5. Notifications</h5>
        <p className="dp-cset__lede">
          DayPilot notifies you about the Slack conversations it classified as needing a reply
          or an action. Everything else waits in the inbox rather than interrupting you — the
          point of the feature is fewer notifications, not another source of them.
        </p>
        <div className="dp-cset__row dp-cset__row--locked">
          <span className="dp-cset__locked-label">Mentions</span>
          <span className="dp-cset__ok">Immediate</span>
        </div>
        <div className="dp-cset__row dp-cset__row--locked">
          <span className="dp-cset__locked-label">Other traced messages</span>
          <span className="dp-cset__ok">Daily summary</span>
        </div>
      </section>
    </div>
  )
}
