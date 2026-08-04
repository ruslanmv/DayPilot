import type { DayPilotDesignBundle, DayPilotDesignReview } from '@daypilot/shared-types'

/** Seed Matrix Designer bundle + review until live data is wired. */
export const DESIGN_BUNDLE: DayPilotDesignBundle = {
  bundleId: 'bundle-daypilot-mobile',
  title: 'DayPilot Mobile Today View',
  framework: 'React PWA',
  visualTarget: 'HomePilot Family — calm obsidian, accent-as-telemetry',
  architecture: 'Command-first shell with bottom-tab navigation',
  acceptanceCriteria: ['Installable PWA', 'Now/Blocked/Approvals cards', 'Offline last snapshot'],
  validationStatus: 'approved',
  batches: [
    { id: '1', title: 'PWA shell + manifest', description: 'Installable app shell and service worker.', dependsOn: [], acceptance: ['Lighthouse installable'], estimateHours: 6, allowedFiles: [], mustNotChange: [] },
    { id: '2', title: 'Today cards', description: 'Now / Next / Blocked / AI Running / Approvals.', dependsOn: ['1'], acceptance: ['Cards render from /v1/today'], estimateHours: 8, allowedFiles: [], mustNotChange: [] },
    { id: '3', title: 'Push approvals', description: 'Web Push → approval card deep link.', dependsOn: ['2'], acceptance: ['Approve on phone reflects on desktop'], estimateHours: 10, allowedFiles: [], mustNotChange: [] },
  ],
}

export const DESIGN_REVIEW: DayPilotDesignReview = {
  reviewId: 'rev-command',
  target: 'command-screen.png',
  score: 82,
  grade: 'B',
  findings: [
    { severity: 'minor', area: 'spacing', note: 'Tighten Today card vertical rhythm.' },
    { severity: 'major', area: 'contrast', note: 'Muted labels below AA on the strategic feed.' },
  ],
  suggestions: ['Raise --hp-text-muted contrast on dark surfaces', 'Add focus ring to plan blocks'],
  projectId: null,
}
