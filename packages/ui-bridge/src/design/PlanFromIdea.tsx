import React, { useEffect, useState } from 'react'
import type {
  DayPilotDesignCandidate,
  DayPilotDesignProposal,
  DayPilotDesignReview,
} from '@daypilot/shared-types'
import { designApi, type DesignIntake } from './designClient'

type PlanFromIdeaProps = {
  /** Prefills the idea — from the assistant, a note, or nothing. */
  initialIdea?: string
  /** Called once the plan is scheduled, with the project it created. */
  onScheduled: (intake: DesignIntake) => void
  onClose: () => void
}

type Step = 'idea' | 'choose' | 'scheduled'

/**
 * Turn an idea into scheduled work: propose → choose → adjust → schedule.
 *
 * The choice is the point of this surface. Matrix Designer returns three plans
 * for the same idea — simplest to most complete — and picking one genuinely
 * changes the design that follows, so each card shows what living with that plan
 * costs: effort, difficulty, stack, and the batches it breaks into.
 *
 * Nothing is created until the last step. A plan can be adjusted in words as
 * many times as it takes, and the repository is asked for here because that is
 * where the batches will actually be built.
 */
export function PlanFromIdea({ initialIdea = '', onScheduled, onClose }: PlanFromIdeaProps) {
  const [step, setStep] = useState<Step>('idea')
  const [idea, setIdea] = useState(initialIdea)
  const [proposal, setProposal] = useState<DayPilotDesignProposal | null>(null)
  const [chosen, setChosen] = useState('')
  const [adjustment, setAdjustment] = useState('')
  const [repository, setRepository] = useState('')
  const [intake, setIntake] = useState<DesignIntake | null>(null)
  const [check, setCheck] = useState<DayPilotDesignReview | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const candidate = proposal?.candidates.find((c) => c.id === chosen)

  async function propose() {
    setBusy('propose')
    setError('')
    const result = await designApi.blueprints(idea.trim())
    setBusy('')
    if (!result.ok) {
      setError(result.error)
      return
    }
    setProposal(result.value)
    setChosen(result.value.recommendedId || result.value.candidates[0]?.id || '')
    setStep('choose')
  }

  async function adjust() {
    if (!adjustment.trim() || !chosen) return
    setBusy('adjust')
    setError('')
    const result = await designApi.refine(idea.trim(), adjustment.trim(), chosen)
    setBusy('')
    if (!result.ok) {
      setError(result.error)
      return
    }
    setProposal(result.value)
    setCheck(null)
    setAdjustment('')
  }

  /** Governance before the build: the designer's own schema + rule verdict. */
  async function checkPlan() {
    if (!chosen) return
    setBusy('check')
    setError('')
    const result = await designApi.review(idea.trim(), chosen)
    setBusy('')
    if (!result.ok) {
      setError(result.error)
      return
    }
    setCheck(result.value)
  }

  async function schedule() {
    if (!chosen) return
    setBusy('schedule')
    setError('')
    const result = await designApi.build(idea.trim(), chosen, repository.trim())
    setBusy('')
    if (!result.ok) {
      setError(result.error)
      return
    }
    setIntake(result.value.intake || null)
    setStep('scheduled')
  }

  return (
    <div className="dp-modal-backdrop" onMouseDown={onClose}>
      <div
        className="dp-design dp-plan"
        role="dialog"
        aria-modal="true"
        aria-label="Plan from an idea"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="dp-settings-panel__head">
          <h3>
            {step === 'idea' && 'Start from an idea'}
            {step === 'choose' && 'Choose a plan'}
            {step === 'scheduled' && 'Plan scheduled'}
          </h3>
          <button className="dp-icon-button" aria-label="Close" onClick={onClose}>✕</button>
        </header>

        <div className="dp-design__body">
          {step === 'idea' && (
            <div className="dp-settings-list">
              <label className="dp-onb__field">
                <span>What do you want to build?</span>
                <textarea
                  className="dp-plan__idea"
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  rows={4}
                  placeholder="A task manager for a small team, with SSO and a weekly digest"
                  autoFocus
                />
                <small className="dp-onb__hint">
                  Matrix Designer will propose three plans. Nothing is created until you choose one.
                </small>
              </label>
            </div>
          )}

          {step === 'choose' && proposal && (
            <div className="dp-settings-list">
              <ul className="dp-plan__cards" role="radiogroup" aria-label="Candidate plans">
                {proposal.candidates.map((c: DayPilotDesignCandidate) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={chosen === c.id}
                      className={'dp-plan__card' + (chosen === c.id ? ' is-active' : '')}
                      onClick={() => { setChosen(c.id); setCheck(null) }}
                    >
                      <span className="dp-plan__card-head">
                        <strong>{c.tier}</strong>
                        {c.recommended && <span className="dp-pill">Recommended</span>}
                      </span>
                      <span className="dp-plan__summary">{c.summary}</span>
                      <span className="dp-plan__facts">
                        <span>{c.estimate}</span>
                        <span>{c.difficulty}</span>
                        <span>{c.batches.length} batches</span>
                        {c.fileCount > 0 && <span>~{c.fileCount} files</span>}
                      </span>
                      {c.stack.length > 0 && <span className="dp-plan__stack">{c.stack.join(' · ')}</span>}
                    </button>
                  </li>
                ))}
              </ul>

              {candidate && candidate.batches.length > 0 && (
                <details className="dp-plan__roadmap" open>
                  <summary>What building {candidate.tier.toLowerCase()} involves</summary>
                  <ol className="dp-design__batches">
                    {candidate.batches.map((batch) => (
                      <li key={batch.id} className="dp-settings-row">
                        <div className="dp-settings-row__head">
                          <strong>{batch.title}</strong>
                          {batch.dependsOn.length > 0 && (
                            <span className="dp-pill dp-pill--muted">after {batch.dependsOn.join(', ')}</span>
                          )}
                        </div>
                        {batch.description && <p>{batch.description}</p>}
                      </li>
                    ))}
                  </ol>
                </details>
              )}

              <label className="dp-onb__field">
                <span>Change something?</span>
                <div className="dp-plan__adjust">
                  <input
                    value={adjustment}
                    onChange={(e) => setAdjustment(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); adjust() } }}
                    placeholder="Add SSO · drop the mobile app · use Postgres"
                  />
                  <button
                    className="dp-ghost-button"
                    onClick={adjust}
                    disabled={!adjustment.trim() || busy === 'adjust'}
                  >
                    {busy === 'adjust' ? 'Adjusting…' : 'Adjust'}
                  </button>
                </div>
                <small className="dp-onb__hint">The plan is re-proposed; nothing is built yet.</small>
              </label>

              <label className="dp-onb__field">
                <span>Repository to build in</span>
                <input
                  value={repository}
                  onChange={(e) => setRepository(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                />
                <small className="dp-onb__hint">
                  {repository.trim()
                    ? 'Every batch of this plan will be built here.'
                    : 'Optional now — the project will ask for it before the first batch runs.'}
                </small>
              </label>

              <div className="dp-plan__check">
                <button
                  className="dp-ghost-button"
                  onClick={checkPlan}
                  disabled={!chosen || busy === 'check'}
                >
                  {busy === 'check' ? 'Checking…' : 'Check this plan'}
                </button>
                {check && (
                  <span className={'dp-tag dp-tag--' + (check.score >= 75 ? 'healthy' : check.score >= 60 ? 'degraded' : 'offline')}>
                    {check.grade} · {check.score}/100
                  </span>
                )}
              </div>
              {check && check.findings.length > 0 && (
                <ul className="dp-settings-list" aria-label="Design findings">
                  {check.findings.map((finding, i) => (
                    <li key={i} className="dp-settings-row">
                      <div className="dp-settings-row__head">
                        <span className={'dp-tag dp-tag--' + (finding.severity === 'critical' || finding.severity === 'major' ? 'offline' : 'degraded')}>
                          {finding.severity}
                        </span>
                        <strong>{finding.area}</strong>
                      </div>
                      <p>{finding.note}</p>
                    </li>
                  ))}
                </ul>
              )}
              {check && check.findings.length === 0 && (
                <p className="dp-muted">No design-rule violations — this plan is buildable as it stands.</p>
              )}

              {proposal.violations.length > 0 && (
                <p className="dp-muted">
                  Designer notes: {proposal.violations.map((v) => v.message).filter(Boolean).join(' · ')}
                </p>
              )}
              {proposal.reply && <p className="dp-muted">{proposal.reply}</p>}
            </div>
          )}

          {step === 'scheduled' && (
            <div className="dp-settings-list">
              <div className="dp-settings-row">
                <strong>{intake?.projectName || 'Project created'}</strong>
                <p>
                  {intake
                    ? `${intake.batches} batches scheduled in dependency order — the first is active, the rest wait on it.`
                    : 'The plan was designed but no work was scheduled.'}
                </p>
                {intake?.repository ? (
                  <p className="dp-muted">Building in {intake.repository}</p>
                ) : (
                  <p className="dp-muted">No repository yet — add one before starting the first batch.</p>
                )}
              </div>
            </div>
          )}

          {error && <p className="dp-plan__error" role="alert">{error}</p>}
        </div>

        <footer className="dp-pw__foot">
          {step === 'idea' && (
            <>
              <button className="dp-onb__back" onClick={onClose}>Cancel</button>
              <button
                className="dp-onb__next"
                onClick={propose}
                disabled={!idea.trim() || busy === 'propose'}
              >
                {busy === 'propose' ? 'Designing…' : 'Propose plans'}
              </button>
            </>
          )}
          {step === 'choose' && (
            <>
              <button className="dp-onb__back" onClick={() => setStep('idea')}>Back</button>
              <button
                className="dp-onb__next"
                onClick={schedule}
                disabled={!chosen || busy === 'schedule'}
              >
                {busy === 'schedule' ? 'Scheduling…' : 'Schedule this plan'}
              </button>
            </>
          )}
          {step === 'scheduled' && (
            <>
              <button className="dp-onb__back" onClick={onClose}>Close</button>
              <button
                className="dp-onb__next"
                onClick={() => intake && onScheduled(intake)}
                disabled={!intake}
              >
                Open the project
              </button>
            </>
          )}
        </footer>
      </div>
    </div>
  )
}
