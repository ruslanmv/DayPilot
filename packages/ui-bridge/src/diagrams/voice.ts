/**
 * Dictation (batch C3) through the browser's own speech recognition. Audio is handled by the
 * browser; DayPilot only ever receives the recognised text, which the person can edit before use.
 */
type Recognition = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
}
type Ctor = new () => Recognition

export function speechSupported(): boolean {
  const w = globalThis as unknown as { SpeechRecognition?: Ctor; webkitSpeechRecognition?: Ctor }
  return typeof window !== 'undefined' && !!(w.SpeechRecognition || w.webkitSpeechRecognition)
}

/** Turn spoken sentences into outline lines: one idea per sentence, spoken "new line" breaks one. */
export function transcriptToOutline(text: string): string {
  return text
    .replace(/\b(?:new line|next line)\b[.,]?/gi, '\n')
    .split(/\n|(?<=[.!?])\s+/)
    .map((s) => s.replace(/\s+/g, ' ').trim().replace(/[.!?]+$/, ''))
    .filter(Boolean)
    .map((s) => s[0].toUpperCase() + s.slice(1))
    .join('\n')
}

export type Dictation = { stop: () => void }

/** Start dictating; `onText` gets the full transcript so far. Returns null where unsupported. */
export function startDictation(
  lang: string,
  onText: (text: string, final: boolean) => void,
  onEnd: (error?: string) => void,
): Dictation | null {
  const w = globalThis as unknown as { SpeechRecognition?: Ctor; webkitSpeechRecognition?: Ctor }
  const Impl = w.SpeechRecognition || w.webkitSpeechRecognition
  if (!Impl) return null
  const rec = new Impl()
  rec.lang = lang
  rec.continuous = true
  rec.interimResults = true
  let finals = ''
  let failure: string | undefined
  rec.onresult = (e) => {
    let interim = ''
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]
      if (r.isFinal) finals += r[0].transcript + ' '
      else interim += r[0].transcript
    }
    onText((finals + interim).trim(), !interim)
  }
  rec.onerror = (e) => {
    failure = e.error === 'not-allowed' ? 'Microphone access was blocked. Allow it in the browser to dictate.' : e.error === 'no-speech' ? undefined : `Dictation stopped (${e.error}).`
  }
  rec.onend = () => onEnd(failure)
  rec.start()
  return { stop: () => rec.stop() }
}
