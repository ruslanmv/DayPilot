/**
 * Starting points that need no AI and no network (batch C3): a template gallery and brainstorming
 * modes. Each yields an outline (one idea per line, two spaces per level) that goes through the same
 * outline parser and preview as anything the person types, so nothing is special-cased.
 */
import type { DiagramKind } from './dmind'

export type Template = { id: string; name: string; kind: DiagramKind; blurb: string; outline: string }
export type BrainstormMode = { id: string; name: string; blurb: string; build: (topic: string) => string }

export const TEMPLATES: Template[] = [
  { id: 'project-plan', name: 'Project plan', kind: 'mindmap', blurb: 'Goals, scope, phases, risks and owners',
    outline: 'Goals\n  Outcome\n  Success measures\nScope\n  In scope\n  Out of scope\nPhases\n  Discover\n  Build\n  Launch\nRisks\n  Biggest unknown\n  Dependencies\nPeople\n  Owner\n  Reviewers' },
  { id: 'swot', name: 'SWOT analysis', kind: 'mindmap', blurb: 'Strengths, weaknesses, opportunities, threats',
    outline: 'Strengths\n  What we do well\n  Unique assets\nWeaknesses\n  Gaps\n  Constraints\nOpportunities\n  Trends\n  Unmet needs\nThreats\n  Competitors\n  External changes' },
  { id: 'meeting-notes', name: 'Meeting notes', kind: 'mindmap', blurb: 'Agenda, decisions, actions',
    outline: 'Agenda\n  Topic 1\n  Topic 2\nDecisions\n  Decision and why\nAction items\n  Who does what by when\nOpen questions' },
  { id: 'weekly-plan', name: 'Weekly plan', kind: 'mindmap', blurb: 'Priorities, days, follow-ups',
    outline: 'Top 3 priorities\n  First\n  Second\n  Third\nMonday\nTuesday\nWednesday\nThursday\nFriday\nFollow-ups\n  Waiting on others\n  To schedule' },
  { id: 'okr', name: 'OKRs', kind: 'mindmap', blurb: 'Objective with measurable key results',
    outline: 'Objective\n  Key result 1\n    Metric and target\n  Key result 2\n    Metric and target\n  Key result 3\n    Metric and target\nInitiatives\n  What we will do\nRisks' },
  { id: 'product-launch', name: 'Product launch', kind: 'mindmap', blurb: 'Audience, message, channels, checklist',
    outline: 'Audience\n  Who it is for\n  Their problem\nMessage\n  One-line promise\n  Proof\nChannels\n  Email\n  Social\n  Press\nLaunch checklist\n  Product ready\n  Support ready\n  Announcement\nAfter launch\n  Measure\n  Learn' },
  { id: 'decision', name: 'Decision', kind: 'mindmap', blurb: 'Options with pros and cons',
    outline: 'Decision to make\n  Option A\n    Pros\n    Cons\n  Option B\n    Pros\n    Cons\nCriteria\n  What matters most\nRecommendation\nNext step' },
  { id: 'retro', name: 'Retrospective', kind: 'mindmap', blurb: 'Went well, to improve, actions',
    outline: 'Went well\n  Keep doing\nTo improve\n  Pain points\nIdeas\n  Experiments\nActions\n  Owner and date' },
  { id: 'study', name: 'Study notes', kind: 'mindmap', blurb: 'Concepts, examples, questions, summary',
    outline: 'Key concepts\n  Concept 1\n  Concept 2\nExamples\nQuestions\n  What I do not understand\nSummary in one sentence\nRelated topics' },
  { id: 'user-journey', name: 'User journey', kind: 'flowchart', blurb: 'Steps from awareness to loyalty',
    outline: 'Aware of the product\nVisits the site\nSigns up\nFirst success\nComes back\nRecommends' },
  { id: 'approval-flow', name: 'Approval flow', kind: 'flowchart', blurb: 'Request, review, decision, outcome',
    outline: 'Request submitted\nManager reviews\nApproved?\nPublish or fulfil\nReturn with comments' },
  { id: 'bug-triage', name: 'Bug triage', kind: 'flowchart', blurb: 'Report to fix to release',
    outline: 'Bug reported\nReproduce\nAssess severity\nAssign owner\nFix and test\nRelease\nVerify and close' },
  { id: 'system-design', name: 'System design', kind: 'system', blurb: 'Clients, services, data, operations',
    outline: 'System\n  Clients\n    Web app\n    Mobile app\n  Services\n    API\n    Background jobs\n  Data\n    Database\n    Cache\n  Operations\n    Monitoring\n    Deployment' },
  { id: 'trip', name: 'Trip planning', kind: 'mindmap', blurb: 'Where, when, stay, getting around, packing',
    outline: 'Destination\n  Dates\n  Budget\nTransport\n  Getting there\n  Getting around\nStay\n  Options\nThings to do\nPacking\n  Documents\n  Clothes' },
]

const clean = (topic: string) => topic.replace(/\s+/g, ' ').trim().slice(0, 120) || 'the topic'

export const BRAINSTORM_MODES: BrainstormMode[] = [
  { id: 'free', name: 'Free branches', blurb: 'Who, what, why, how, when, where',
    build: (t) => `Who is involved with ${clean(t)}?\nWhat is it?\nWhy does it matter?\nHow could it work?\nWhen does it need to happen?\nWhere does it apply?` },
  { id: 'scamper', name: 'SCAMPER', blurb: 'Seven prompts to change an idea',
    build: (t) => ['Substitute', 'Combine', 'Adapt', 'Modify', 'Put to another use', 'Eliminate', 'Reverse'].map((p) => `${p}\n  What could we ${p.toLowerCase()} in ${clean(t)}?`).join('\n') },
  { id: 'five-whys', name: '5 Whys', blurb: 'Dig to a root cause',
    build: (t) => `Problem: ${clean(t)}\n  Why does it happen?\n    Why is that?\n      Why is that?\n        Why is that?\n          Why is that?\n            Root cause\n            What would fix it?` },
  { id: 'pros-cons', name: 'Pros and cons', blurb: 'Both sides of a choice',
    build: (t) => `${clean(t)}\n  Pros\n    Benefit 1\n    Benefit 2\n  Cons\n    Cost 1\n    Cost 2\n  Verdict` },
  { id: 'six-hats', name: 'Six thinking hats', blurb: 'Six viewpoints on one topic',
    build: (t) => `${clean(t)}\n  White: facts and data\n  Red: feelings and instincts\n  Black: risks and cautions\n  Yellow: benefits and value\n  Green: new ideas\n  Blue: process and next steps` },
  { id: 'pre-mortem', name: 'Risks (pre-mortem)', blurb: 'Imagine it failed: why?',
    build: (t) => `Imagine ${clean(t)} failed\n  What went wrong?\n    People\n    Time\n    Money\n    Technology\n  Early warning signs\n  How we prevent it` },
  { id: 'stakeholders', name: 'Stakeholders', blurb: 'Who is affected and what they need',
    build: (t) => `${clean(t)}\n  Decision makers\n    What they need\n  Doers\n    What they need\n  Affected people\n    What they need\n  Critics\n    Their concerns` },
]

export const templateById = (id: string) => TEMPLATES.find((t) => t.id === id)
export const modeById = (id: string) => BRAINSTORM_MODES.find((m) => m.id === id)
