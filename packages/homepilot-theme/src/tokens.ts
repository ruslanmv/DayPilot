/**
 * HomePilot Family tokens for JavaScript/TypeScript consumers.
 *
 * Mirrors tokens.css so charts, canvas, inline styles, and non-CSS surfaces
 * read the same values. CSS remains the source of truth for the DOM; this file
 * is the source of truth for code that cannot reach a CSS variable.
 */

export const color = {
  bg: '#080c14',
  bgAlt: '#090d16',
  surface: '#111625',
  surfaceElevated: '#151b2b',
  surfaceGlass: 'rgba(17, 22, 37, 0.58)',
  border: 'rgba(255, 255, 255, 0.06)',
  borderStrong: 'rgba(255, 255, 255, 0.11)',
  text: '#f8fafc',
  textMuted: '#94a3b8',
  textFaint: '#64748b',
  accentBlue: '#007aff',
  accentCyan: '#00f0ff',
  accentPurple: '#af52de',
  accentOrange: '#ff9500',
  accentGreen: '#34c759',
  accentRed: '#ff3b30',
  focusRing: 'rgba(175, 82, 222, 0.55)',
} as const

export const font = {
  sans: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  mono: 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace',
} as const

export const radius = {
  sm: '8px',
  md: '12px',
  lg: '18px',
  pill: '999px',
} as const

export const space = {
  1: '0.25rem',
  2: '0.45rem',
  3: '0.62rem',
  4: '0.9rem',
  5: '1.1rem',
  6: '1.4rem',
  8: '2rem',
} as const

export const shadow = {
  sm: '0 1px 2px rgba(0, 0, 0, 0.3)',
  md: '0 10px 30px rgba(0, 0, 0, 0.35)',
  lg: '0 24px 60px rgba(0, 0, 0, 0.45)',
} as const

export const blur = {
  sm: '12px',
  md: '28px',
  lg: '40px',
} as const

/** Breakpoint maxima in px. `wide` is a lower bound. */
export const breakpoint = {
  phone: 640,
  tablet: 1024,
  desktop: 1440,
  wide: 1440,
} as const

export type ColorToken = keyof typeof color
