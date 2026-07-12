import type { DayPilotEmailFolder } from '@daypilot/shared-types'

export const EMAIL_FOLDERS: Array<DayPilotEmailFolder & { icon: string }> = [
  { name: 'Inbox', count: 18, icon: '📥' },
  { name: 'Drafts', count: 3, icon: '📝' },
  { name: 'Sent', icon: '📤' },
  { name: 'Archive', icon: '🗄' },
  { name: 'Important', icon: '⭐' },
]

export type MailMessage = {
  id: string
  sender: string
  senderName: string
  subject: string
  preview: string
  time: string
  unread: boolean
  hasAttachment: boolean
  intent: 'scheduling' | 'incident' | 'informational'
  body: string[]
}

export const EMAIL_ITEMS: MailMessage[] = [
  {
    id: 'e1', sender: 'pm@clientalpha.com', senderName: 'Morgan Parker',
    subject: 'Client Alpha proposal — deadline change', time: '10:24 AM',
    unread: true, hasAttachment: true, intent: 'scheduling',
    preview: "We'd like to move delivery from Friday to Monday, and add a weekly reporting requirement.",
    body: [
      "We'd like to move delivery from Friday to Monday, and add a weekly reporting requirement.",
      "Due to additional scope requested by the client and dependencies on the design review, we won't be able to deliver by the original date.",
      'Please let me know if this works or if you see any risks.',
      'Best regards,\npm',
    ],
  },
  {
    id: 'e2', sender: 'ci@github.com', senderName: 'GitPilot CI',
    subject: 'GitPilot build failure on api branch', time: '9:58 AM',
    unread: true, hasAttachment: false, intent: 'incident',
    preview: 'The pipeline failed on feature/api-gateway-tests: 2 tests failing.',
    body: ['The pipeline failed on feature/api-gateway-tests: 2 tests failing.', 'See the attached logs for the stack traces.'],
  },
  {
    id: 'e3', sender: 'design@matrix.dev', senderName: 'Matrix Designer',
    subject: 'Matrix Designer: 3 UI recommendations', time: '9:14 AM',
    unread: true, hasAttachment: false, intent: 'informational',
    preview: 'Contrast on nav labels, card spacing, and a focus ring suggestion.',
    body: ['Contrast on nav labels, card spacing, and a focus ring suggestion.'],
  },
  {
    id: 'e4', sender: 'ops@daypilot.io', senderName: 'Operations',
    subject: 'Weekly infrastructure report', time: 'Yesterday',
    unread: false, hasAttachment: true, intent: 'informational',
    preview: 'All systems operational. See attached summary and charts.',
    body: ['All systems operational. See attached summary and charts.'],
  },
  {
    id: 'e5', sender: 'noreply@slack.com', senderName: 'Slack',
    subject: 'You have 5 new mentions', time: 'Yesterday',
    unread: false, hasAttachment: false, intent: 'informational',
    preview: "See what's happening in your channels.",
    body: ["See what's happening in your channels."],
  },
  {
    id: 'e6', sender: 'alerts@daypilot.io', senderName: 'Alerts',
    subject: 'Alert: High API error rate detected', time: 'May 15',
    unread: false, hasAttachment: false, intent: 'incident',
    preview: 'We detected a spike in 5xx errors on the Billing service.',
    body: ['We detected a spike in 5xx errors on the Billing service.'],
  },
  {
    id: 'e7', sender: 'qa@daypilot.io', senderName: 'QA',
    subject: 'Test plan for v2.4', time: 'May 15',
    unread: false, hasAttachment: true, intent: 'informational',
    preview: 'Please review the attached test plan for the upcoming release.',
    body: ['Please review the attached test plan for the upcoming release.'],
  },
]
