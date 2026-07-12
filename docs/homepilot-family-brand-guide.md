# HomePilot Family Brand & Design Guide

DayPilot is part of the **HomePilot Family**. HomePilot governs local, personal
AI; DayPilot governs professional workflows. They must feel like one system:
the same calm, premium obsidian workspace, the same restrained accent language,
the same words for the same states. This guide is the contract that keeps them
aligned.

The tokens described here are implemented in
[`packages/homepilot-theme`](../packages/homepilot-theme) and consumed by
DayPilot through `packages/ui-bridge/src/space-bridge.css`.

## 1. Principles

1. **Calm over dense.** Show Now, Next, Blocked, AI Running, and Needs Approval
   by default. Everything else lives in drawers and detail views.
2. **Premium, not decorative.** Obsidian surfaces, generous spacing, one clear
   type hierarchy. No gradients-as-decoration, no enterprise clutter.
3. **Color is telemetry, never ornament.** The accent palette exists to signal
   state. If a color is not communicating a state, it should not be there.
4. **Local-first is visible.** The family's privacy posture is a first-class
   state, not fine print.
5. **Motion communicates change.** Animations mark a transition (a block starts,
   an approval arrives) at calm amplitudes, and always yield to
   `prefers-reduced-motion`.
6. **One language across surfaces.** A state looks and reads identically in
   Command, Agents, Documents, and Approvals — and identically in HomePilot.

## 2. Token contract

Canonical variables use the shared `--hp-*` prefix. DayPilot's legacy `--dp-*`
variables are thin aliases onto them, so a palette change propagates everywhere
from one file. **Never hard-code a palette value in a component stylesheet** —
reference a token.

### Color

| Token | Value | Use |
|---|---|---|
| `--hp-bg` / `--hp-bg-alt` | `#080c14` / `#090d16` | App background |
| `--hp-surface` / `--hp-surface-elevated` | `#111625` / `#151b2b` | Cards, panels |
| `--hp-surface-glass` | `rgba(17,22,37,.58)` | Drawers, rails (with blur) |
| `--hp-border` / `--hp-border-strong` | white @ 6% / 11% | Hairlines, dividers |
| `--hp-text` / `--hp-text-muted` / `--hp-text-faint` | `#f8fafc` / `#94a3b8` / `#64748b` | Text hierarchy |
| `--hp-accent-blue` | `#007aff` | Primary / active |
| `--hp-accent-cyan` | `#00f0ff` | AI signal / info |
| `--hp-accent-purple` | `#af52de` | Persona / planner |
| `--hp-accent-orange` | `#ff9500` | Warning / needs attention |
| `--hp-accent-green` | `#34c759` | Safe / success |
| `--hp-accent-red` | `#ff3b30` | Escalation / blocked |

### Typography, spacing, radii, elevation, blur, motion

- **Type:** `--hp-font-sans` (Apple system stack) and `--hp-font-mono`; scale
  `--hp-text-2xs … --hp-text-2xl`; weights `--hp-weight-normal|medium|strong`.
  Eyebrows are mono, uppercase, `--hp-tracking-eyebrow`, in `--hp-accent-cyan`.
- **Spacing:** `--hp-space-1 … --hp-space-8`. Prefer the scale over ad-hoc rem.
- **Radii:** `--hp-radius-sm|md|lg|pill`. Pills for nav and status chips.
- **Elevation:** `--hp-shadow-sm|md|lg`. Reserve `lg` for overlays/drawers.
- **Blur:** `--hp-blur-sm|md|lg` for glass surfaces.
- **Motion:** durations `--hp-motion-fast|base|slow`; easings
  `--hp-ease-standard|entrance|exit`. Names inherited from HomePilot: `fadeIn`,
  `slideIn`, `glowPulse` — used at calmer amplitudes than HomePilot's studio.

## 3. State language

Six states recur across the product. Each has one color, one glyph, one label —
defined once in [`state.ts`](../packages/homepilot-theme/src/state.ts) and driven
by `--hp-state-*` CSS variables. Render them identically everywhere.

| State | Color | Glyph | Label | Meaning |
|---|---|---|---|---|
| `local-first` | green | 🔒 | Local-first | Runs and stays on-device unless cloud sync is enabled. |
| `approval-gated` | orange | ✋ | Needs approval | A sensitive action is queued until you approve it. |
| `ai-running` | cyan | ◐ | AI running | An agent is actively working this item. |
| `blocked` | red | ⛔ | Blocked | Cannot proceed until a dependency/decision/error is resolved. |
| `safe` | green | ✓ | Safe | Completed or verified, no outstanding risk. |
| `needs-attention` | orange | ⚠ | Needs attention | At risk or drifting; review recommended, not blocking. |

The emoji glyphs are placeholders for a monochrome icon set; the color, label,
and meaning are the contract.

## 4. Breakpoints

DayPilot is a desktop command center and a portable phone companion. Layouts are
driven by four breakpoints (see `breakpoint` in
[`tokens.ts`](../packages/homepilot-theme/src/tokens.ts)):

| Name | Range | Layout |
|---|---|---|
| Phone | `< 640px` | Single column, bottom tab bar, summary cards. Settings menu anchors from the tab bar. |
| Tablet | `640–1024px` | Collapsible rail, two panes. |
| Desktop | `1024–1440px` | Rail + multipane command center with right-edge drawer. |
| Wide | `≥ 1440px` | Desktop layout with wider feed and drawer. |

Validate every screen at phone, tablet, and desktop widths. The page body must
never scroll horizontally; wide content scrolls inside its own container.

## 5. Do / don't

**Do**
- Reference `--hp-*` (or the `--dp-*` aliases) tokens for every color, radius,
  space, and shadow.
- Use accent colors only to express a state from the table above.
- Keep the default view calm; push detail into drawers.
- Provide a reduced-motion path for every animation.

**Don't**
- Hard-code hex values or ad-hoc pixel spacing in component CSS.
- Use more than one accent color in a single component without a state reason.
- Introduce a new state word for an existing state — extend the language in
  `state.ts` instead.
- Add drop shadows or blurs heavier than the `lg` tokens.

## 6. Consuming the theme

```ts
// CSS variables for the DOM (import once at the app root):
import '@daypilot/homepilot-theme/tokens.css'

// TS tokens for canvas/charts/inline styles that cannot reach CSS variables:
import { color, STATE_LANGUAGE, transition } from '@daypilot/homepilot-theme'
```

CSS is the source of truth for the DOM; `tokens.ts` is the source of truth for
code that cannot read a CSS variable. Keep the two in sync — a change to one is
a change to both.
