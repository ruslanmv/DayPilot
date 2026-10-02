/**
 * Fictional starting points: a neutral DayPilot kit and two clearly fictional company kits used
 * by tests and the sample gallery. No real company's assets are represented.
 */
const type = (head, body) => ({
  deck_title: { family: head, minimum_pt: 36, preferred_pt: 44, fallbacks: [] },
  slide_title: { family: head, minimum_pt: 26, preferred_pt: 32, fallbacks: [] },
  body: { family: body, minimum_pt: 16, preferred_pt: 20, fallbacks: [] },
  data: { family: body, minimum_pt: 14, preferred_pt: 18, fallbacks: [] },
  footnote: { family: body, minimum_pt: 11, preferred_pt: 12, fallbacks: [] },
})

export function defaultBrandKit(companyId = 'company_default', name = 'DayPilot') {
  return {
    schema_version: 'daypilot.brand-kit/v1', id: `${companyId}_brand`, company_id: companyId, company_name: name, version: 1,
    slide_size: { width_inches: 13.333, height_inches: 7.5 },
    palette: { background: '#FFFFFF', foreground: '#1B2333', primary: '#1F3A93', accent: '#0FA3B1', muted: '#5B6474', positive: '#1E7F4F', warning: '#9A5B00', negative: '#B3261E' },
    typography: type('Calibri', 'Calibri'),
    logos: [], allowed_fonts: ['Calibri', 'Cambria', 'Arial'],
    chart_style: { series_colors: ['#1F3A93', '#0FA3B1', '#8E9AAF'], minimum_label_pt: 14, allow_3d: false },
    footer: { text: `${name} · Internal`, required: true, show_page_number: true },
    activation_policy: 'sample_review_required',
  }
}

export const SAMPLE_KITS = {
  northwind: () => ({
    ...defaultBrandKit('company_northwind', 'Northwind Analytics (fictional)'),
    id: 'northwind_brand',
    palette: { background: '#FFFFFF', foreground: '#14213D', primary: '#0B3C5D', accent: '#E07A1F', muted: '#56606E', positive: '#1E7F4F', warning: '#9A5B00', negative: '#B3261E' },
    typography: type('Cambria', 'Calibri'),
    chart_style: { series_colors: ['#0B3C5D', '#E07A1F', '#8FA8BF'], minimum_label_pt: 14, allow_3d: false },
    footer: { text: 'Northwind Analytics · FICTIONAL · Internal', required: true, show_page_number: true },
  }),
  verdant: () => ({
    ...defaultBrandKit('company_verdant', 'Verdant Labs (fictional)'),
    id: 'verdant_brand',
    palette: { background: '#FFFFFF', foreground: '#1D2B24', primary: '#2C5F2D', accent: '#7A4CC2', muted: '#55605A', positive: '#2C7A3F', warning: '#97600A', negative: '#B0302A' },
    typography: type('Arial', 'Arial'),
    chart_style: { series_colors: ['#2C5F2D', '#7A4CC2', '#97BC62'], minimum_label_pt: 14, allow_3d: false },
    footer: { text: 'Verdant Labs · FICTIONAL · Confidential draft', required: true, show_page_number: true },
  }),
}

/** A weekly report storyline that exercises every layout (fictional numbers). */
export function weeklySample(week = 'Week 39 · 21–27 Sep 2026') {
  return {
    schema_version: 'daypilot.storyline/v1',
    title: 'Weekly delivery review',
    subtitle: 'What shipped, what slipped and the decision we need',
    audience: 'Leadership team',
    purpose: 'Weekly status and one decision',
    sources: [{ id: 'metrics', label: 'Delivery metrics export (fictional)', kind: 'metric_extract', metrics: [
      { id: 'accepted', value: 25, unit: 'items', definition: 'Accepted work items', locator: 'fixture:/accepted' },
      { id: 'cycle', value: 3.2, unit: 'days', definition: 'Median cycle time', locator: 'fixture:/cycle' },
    ] }],
    slides: [
      { id: 'cover', type: 'cover', title: 'Weekly delivery review', subtitle: 'What shipped, what slipped and the decision we need', kicker: week },
      { id: 'agenda', type: 'agenda', title: 'Agenda', items: ['Highlights', 'Throughput and quality', 'Risks and mitigations', 'Roadmap', 'Decision needed'] },
      { id: 'kpis', type: 'kpis', title: 'The week in numbers', kpis: [
        { value: '25', label: 'Work items accepted', delta: '+4 vs last week', metric_ref: { source_snapshot_id: 'metrics', metric_id: 'accepted' }, numeric_value: 25, unit: 'items' },
        { value: '3.2 d', label: 'Median cycle time', delta: '−0.4 d vs last week', metric_ref: { source_snapshot_id: 'metrics', metric_id: 'cycle' }, numeric_value: 3.2, unit: 'days' },
        { value: '98.6%', label: 'Release success rate', delta: 'Flat' },
      ], footnote: 'Fictional data for illustration. Deltas compare equal 7-day windows.' },
      { id: 'throughput', type: 'chart', title: 'Throughput peaked on Friday after the release freeze lifted', chart: { type: 'column', title: 'Accepted items per day', unit: 'items', categories: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri'], series: [{ name: 'Accepted', values: [4, 5, 3, 6, 7] }] }, insights: ['Friday was the busiest day: 7 items.', 'Wednesday dipped while the freeze was in place.', 'Total: 25 items, all reviewed.'] },
      { id: 'trend', type: 'chart', title: 'Cycle time is falling for the third week', chart: { type: 'line', title: 'Median cycle time by week', unit: 'days', categories: ['W35', 'W36', 'W37', 'W38', 'W39'], series: [{ name: 'This team', values: [4.4, 4.1, 3.9, 3.6, 3.2] }, { name: 'Target', values: [3.5, 3.5, 3.5, 3.5, 3.5] }] } },
      { id: 'section_risks', type: 'section', title: 'Risks and mitigations', subtitle: 'Two risks need attention this week' },
      { id: 'risks', type: 'table', title: 'Open risks', headers: ['Risk', 'Impact', 'Owner', 'Mitigation'], rows: [
        ['Payment provider API change', 'High', 'Platform', 'Adapter behind a flag by Wed'], ['Two engineers on leave', 'Medium', 'Delivery', 'Defer search tuning one week'], ['Flaky end-to-end suite', 'Low', 'QA', 'Quarantine owner rotation'],
      ] },
      { id: 'options', type: 'comparison', title: 'Two ways to absorb the API change', left: { heading: 'Adapt now', points: ['Ship the adapter this sprint', 'No customer-visible change', 'Delays search tuning one week'] }, right: { heading: 'Wait for v2', points: ['Keeps the sprint plan', 'Risk of outage at provider cut-over', 'Needs a rollback plan'] } },
      { id: 'flow', type: 'diagram', title: 'How a change reaches customers', nodes: [{ id: 'plan', label: 'Plan' }, { id: 'build', label: 'Build' }, { id: 'review', label: 'Review' }, { id: 'release', label: 'Release' }, { id: 'monitor', label: 'Monitor' }], edges: [{ from: 'plan', to: 'build' }, { from: 'build', to: 'review' }, { from: 'review', to: 'release', label: 'approved' }, { from: 'release', to: 'monitor' }] },
      { id: 'roadmap', type: 'timeline', title: 'Roadmap to the October release', milestones: [{ label: 'Adapter behind flag', date: 'Sep 30' }, { label: 'Search tuning', date: 'Oct 7' }, { label: 'Beta with 3 customers', date: 'Oct 14' }, { label: 'General availability', date: 'Oct 28' }] },
      { id: 'decision', type: 'decision', title: 'Decision needed today', recommendation: 'Adapt to the new payment API now and move search tuning one week.', options: ['Adapt now (recommended)', 'Wait for provider v2', 'Split the team across both'], ask: 'Approve the one-week shift by Friday.' },
      { id: 'closing', type: 'closing', title: 'Next week', subtitle: 'Owners confirm by Monday stand-up', next_steps: ['Ship the payment adapter behind a flag', 'Re-plan search tuning for W41', 'Publish the beta invite list'] },
    ],
  }
}
