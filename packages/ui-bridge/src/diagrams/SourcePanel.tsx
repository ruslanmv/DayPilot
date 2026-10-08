import React, { useEffect, useRef, useState } from 'react'
import {
  diagramsApi,
  type Extracted,
  type InputCapabilities,
} from './diagramsClient'
import { describeSource, type SourceText } from './provenance'

const DOCUMENT_TYPES = '.docx,.pdf,.png,.jpg,.jpeg,.gif,.webp,.tif,.tiff,.bmp,.txt,.md,.markdown'

/**
 * Documents and web pages as sources (batch B3). Everything is extracted on the server, shown here
 * for review, and only enters the outline when the person presses "Use this text".
 */
export function SourcePanel({
  sources,
  onUse,
  onRemove,
  disabled,
}: {
  sources: SourceText[]
  onUse: (extracted: Extracted) => void
  onRemove: (id: string) => void
  disabled?: boolean
}) {
  const file = useRef<HTMLInputElement>(null)
  const [caps, setCaps] = useState<InputCapabilities | null>(null)
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<Extracted | null>(null)

  useEffect(() => {
    let live = true
    void diagramsApi.inputCapabilities().then((r) => live && r.ok && setCaps(r.data))
    return () => {
      live = false
    }
  }, [])

  async function run(job: () => ReturnType<typeof diagramsApi.extract>) {
    setBusy(true)
    setError('')
    setPreview(null)
    const r = await job()
    setBusy(false)
    if (r.ok) setPreview(r.data)
    else setError(r.error)
  }
  function pick(f?: File) {
    if (!f) return
    if (caps && f.size > caps.limits.fileBytes) {
      setError(`Use a file smaller than ${Math.round(caps.limits.fileBytes / 1_000_000)} MB.`)
    } else void run(() => diagramsApi.extract(f))
    if (file.current) file.current.value = ''
  }

  return (
    <div className="dmind-sources">
      <h4>Add a document or web page</h4>
      <input
        ref={file}
        className="dmind-file"
        type="file"
        accept={DOCUMENT_TYPES}
        aria-label="Add a document"
        onChange={(e) => pick(e.target.files?.[0])}
      />
      <button disabled={busy || disabled} onClick={() => file.current?.click()}>
        Add a document (DOCX, PDF, image)
      </button>
      {caps && (!caps.pdf || !caps.ocr) && (
        <p className="dmind-hint">
          {!caps.pdf && 'PDF extraction is not installed on this server. '}
          {!caps.ocr && 'Reading text from images is not installed on this server.'}
        </p>
      )}
      <label>
        Web page address
        <input
          type="url"
          value={url}
          maxLength={2048}
          disabled={!caps?.urlFetch}
          placeholder="https://example.org/spec"
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      <button
        disabled={busy || disabled || !caps?.urlFetch || !url.trim()}
        onClick={() => void run(() => diagramsApi.fetchUrl(url.trim()))}
      >
        Fetch page
      </button>
      <p className="dmind-hint">
        {caps?.urlFetch
          ? 'The DayPilot server downloads this page when you press Fetch. Nothing is fetched automatically.'
          : 'Fetching web pages is turned off on this server. An administrator can enable it.'}
      </p>
      {busy && <p role="status">Reading…</p>}
      {error && (
        <p role="alert" className="dmind-error">
          {error}
        </p>
      )}
      {preview && (
        <section aria-label="Extraction preview" className="dmind-extraction">
          <h4>Extraction preview</h4>
          <p>
            {describeSource({ id: '', ...preview.source })} ·{' '}
            {preview.text.split('\n').length} lines · {preview.text.length.toLocaleString()} characters
          </p>
          {preview.warnings.map((w) => (
            <p key={w} className="dmind-hint">
              {w}
            </p>
          ))}
          <textarea
            readOnly
            rows={8}
            value={preview.text}
            aria-label="Extracted text"
          />
          <p className="dmind-hint">
            Check this text. Indentation becomes branches; each line becomes a topic.
          </p>
          <button
            onClick={() => {
              onUse(preview)
              setPreview(null)
            }}
          >
            Use this text
          </button>
          <button onClick={() => setPreview(null)}>Discard</button>
        </section>
      )}
      {sources.length > 0 && (
        <ul aria-label="Sources">
          {sources.map((s) => (
            <li key={s.ref.id}>
              {describeSource(s.ref)}
              <button
                aria-label={`Remove source ${s.ref.name || s.ref.url || s.ref.id}`}
                onClick={() => onRemove(s.ref.id)}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
