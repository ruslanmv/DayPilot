#!/usr/bin/env node
/**
 * Worker entry point. Reads one JSON request on stdin and writes one JSON reply on stdout.
 *   {"op":"compose","storyline":{…},"kit":{…},"options":{…}}            → {deck, findings}
 *   {"op":"compile","deck":{…},"kit":{…},"assets":{id:{media_type,base64,width,height}},"out":"x.pptx"}
 *                                                                        → {scene, inspection, sha256, bytes}
 *   {"op":"validate-kit","kit":{…}}                                      → {warnings}
 * Errors: {"error": "...", "problems": [...]} with exit code 2 (bad input) or 1 (internal).
 */
import fs from 'node:fs'
import { brandWarnings, checkDeck, compile, compose, inspect, sha256, SpecError, validateBrandKit, validateStoryline } from '../src/index.mjs'

const MAX_INPUT = 25_000_000
let raw = ''
process.stdin.setEncoding('utf8')
for await (const chunk of process.stdin) {
  raw += chunk
  if (raw.length > MAX_INPUT) fail(2, 'request too large')
}
let req
try {
  req = JSON.parse(raw)
} catch {
  fail(2, 'request is not JSON')
}
try {
  if (req.op === 'compose') out(compose(req.storyline, req.kit, req.options ?? {}))
  else if (req.op === 'validate-storyline') out({ ok: !!validateStoryline(req.storyline) })
  else if (req.op === 'validate-kit') out({ warnings: brandWarnings(validateBrandKit(req.kit)) })
  else if (req.op === 'compile') {
    const { pptx, scene } = await compile(req.deck, req.kit, req.assets ?? {})
    if (typeof req.out !== 'string' || !req.out.endsWith('.pptx')) fail(2, 'out must name a .pptx file')
    fs.writeFileSync(req.out, pptx)
    const inspection = await inspect(pptx)
    const digest = sha256(pptx)
    out({ scene, inspection, sha256: digest, bytes: pptx.length, receipt: checkDeck({ deck: req.deck, kit: req.kit, scene, inspection, pptxSha256: digest }) })
  } else fail(2, 'unknown op')
} catch (e) {
  if (e instanceof SpecError) fail(2, e.message, e.problems)
  fail(1, e instanceof Error ? e.message : String(e))
}
function out(v) {
  process.stdout.write(JSON.stringify(v))
  process.exit(0)
}
function fail(code, error, problems) {
  process.stdout.write(JSON.stringify({ error, ...(problems ? { problems } : {}) }))
  process.exit(code)
}
