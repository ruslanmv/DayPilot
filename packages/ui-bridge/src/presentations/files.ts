import { useEffect, useState } from 'react'
import { apiBase, workspaceId } from '../env'

/** Fetch an authorised file with the workspace header (img src and links cannot send headers). */
export async function fetchFile(path: string): Promise<Blob> {
  const res = await fetch(apiBase() + path, { headers: { 'X-Workspace-Id': workspaceId() }, credentials: 'include' })
  if (!res.ok) throw new Error(res.status === 404 ? 'File not found.' : `Download failed (${res.status}).`)
  return res.blob()
}

/** An object URL for an authorised image, revoked when the path changes or the component unmounts. */
export function useBlobUrl(path: string | null): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!path) return setUrl(null)
    let live = true
    let made: string | null = null
    fetchFile(path).then(
      (b) => {
        if (!live) return
        made = URL.createObjectURL(b)
        setUrl(made)
      },
      () => live && setUrl(null),
    )
    return () => {
      live = false
      if (made) URL.revokeObjectURL(made)
    }
  }, [path])
  return url
}

export async function download(path: string, name: string) {
  const blob = await fetchFile(path)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
