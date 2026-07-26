/**
 * Local workspace folder helper (additive, non-destructive).
 *
 * Lets the user pick — or create — a folder with the native OS dialog via the
 * File System Access API (Chromium: the dialog has a built-in "New folder"
 * button). Browsers never expose an absolute filesystem path for security, so we
 * take the chosen folder's *name* and suggest a clean, industry-standard project
 * path the user can confirm/edit. Everywhere the API is unavailable (or the user
 * cancels), the plain text field remains the default and the fallback — nothing
 * about the existing manual-entry flow changes.
 */

/** Conventional root for project knowledge folders (matches the current default). */
export const DEFAULT_WORKSPACE_ROOT = '/data/projects'

/** True when the browser can open a native directory picker. */
export function supportsDirectoryPicker(): boolean {
  return typeof window !== 'undefined'
    && typeof (window as unknown as { showDirectoryPicker?: unknown }).showDirectoryPicker === 'function'
}

/**
 * Industry-standard project folder name: lowercase, hyphen-separated, ASCII-safe.
 * "Q3 Client Reports!" -> "q3-client-reports". Empty input -> "project".
 */
export function slugifyProjectFolder(name: string): string {
  const slug = (name || '')
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')  // strip accents
    .toLowerCase().trim()
    .replace(/[^a-z0-9]+/g, '-')                         // non-alnum -> hyphen
    .replace(/-{2,}/g, '-')                              // collapse repeats
    .replace(/^-+|-+$/g, '')                             // trim hyphens
    .slice(0, 64)
  return slug || 'project'
}

/**
 * Best-practice absolute path suggestion: `<root>/<slug>`. If the user already
 * typed an absolute root, it's respected; the same trailing segment is never
 * doubled (so re-browsing an already-suggested path is idempotent).
 */
export function suggestProjectPath(name: string, current?: string): string {
  const slug = slugifyProjectFolder(name)
  const trimmed = (current || '').trim().replace(/\/+$/, '')
  const root = trimmed.startsWith('/') ? trimmed : DEFAULT_WORKSPACE_ROOT
  if (root.endsWith(`/${slug}`)) return root
  return `${root}/${slug}`
}

export type PickedFolder = { name: string; suggestedPath: string }

/**
 * Open the native folder picker so the user can choose an existing folder or
 * create a new one. Returns the folder name + a best-practice path suggestion,
 * or `null` when the API is unavailable or the user cancels — callers keep the
 * manual text field as the default in that case.
 */
export async function pickWorkspaceFolder(current?: string): Promise<PickedFolder | null> {
  if (!supportsDirectoryPicker()) return null
  try {
    const picker = (window as unknown as {
      showDirectoryPicker: (opts?: { mode?: string; startIn?: string }) => Promise<{ name: string }>
    }).showDirectoryPicker
    const handle = await picker({ mode: 'read', startIn: 'documents' })
    const name = String(handle?.name || '').trim()
    if (!name) return null
    return { name, suggestedPath: suggestProjectPath(name, current) }
  } catch {
    // AbortError (user cancelled) or any picker failure — keep the manual field.
    return null
  }
}
