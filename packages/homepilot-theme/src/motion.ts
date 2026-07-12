/**
 * HomePilot Family motion vocabulary.
 *
 * DayPilot inherits HomePilot's animation names (fadeIn, slideIn, glowPulse)
 * at calmer amplitudes — motion communicates state change, it does not perform.
 * Respect `prefers-reduced-motion`; these values are the ceiling, not a floor.
 */

export const duration = {
  fast: 120,
  base: 220,
  slow: 420,
} as const

export const easing = {
  standard: 'cubic-bezier(0.4, 0, 0.2, 1)',
  entrance: 'cubic-bezier(0.16, 1, 0.3, 1)',
  exit: 'cubic-bezier(0.4, 0, 1, 1)',
} as const

export type MotionName = 'fadeIn' | 'slideIn' | 'glowPulse'

export const transition = (
  property = 'all',
  speed: keyof typeof duration = 'base',
  ease: keyof typeof easing = 'standard',
): string => `${property} ${duration[speed]}ms ${easing[ease]}`
