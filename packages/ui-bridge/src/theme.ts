/**
 * Theme control.
 *
 * DayPilot is **dark by default** — the obsidian workspace is the product's
 * identity and does not follow the OS light preference. A user can switch to
 * light in Settings → Appearance; the choice is persisted and applied by
 * stamping `data-theme` on the document root (the token stylesheet keys its
 * light overrides off `:root[data-theme="light"]`).
 */
export type ThemeMode = 'dark' | 'light'

const STORAGE_KEY = 'daypilot.theme'
const DEFAULT: ThemeMode = 'dark'

export function getTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* ignore */
  }
  return DEFAULT
}

/** Write `data-theme` on <html> so the token overrides take effect. Dark is the
 *  default, so the attribute is only set for light (keeps the markup clean). */
export function applyTheme(mode: ThemeMode): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (mode === 'light') root.setAttribute('data-theme', 'light')
  else root.setAttribute('data-theme', 'dark')
}

export function setTheme(mode: ThemeMode): void {
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    /* ignore */
  }
  applyTheme(mode)
}

/** Apply the persisted (or default-dark) theme. Call once at app start. */
export function initTheme(): ThemeMode {
  const mode = getTheme()
  applyTheme(mode)
  return mode
}
