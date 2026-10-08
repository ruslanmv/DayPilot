#!/usr/bin/env node
/**
 * Sandbox entry for expert builders. Started only by the server, inside a fresh network namespace
 * as an unprivileged user with Node's permission model (read: engine + this run's input folder;
 * write: this run's output folder; no child processes, workers or addons). Never run directly on
 * untrusted code outside that sandbox.
 *   node bin/expert.mjs <inDir> <outFile>     inDir has script.mjs, kit.json, assets.json
 */
import fs from 'node:fs'
import path from 'node:path'
import { pathToFileURL } from 'node:url'
import { checkExpert, runExpert } from '../src/expert.mjs'
import { inspect } from '../src/inspect.mjs'
import { sha256 } from '../src/canonical.mjs'

const [inDir, outFile] = process.argv.slice(2)
const reply = (code, v) => {
  process.stdout.write(JSON.stringify(v))
  process.exit(code)
}
try {
  const kit = JSON.parse(fs.readFileSync(path.join(inDir, 'kit.json'), 'utf8'))
  const assets = JSON.parse(fs.readFileSync(path.join(inDir, 'assets.json'), 'utf8'))
  const mod = await import(pathToFileURL(path.join(inDir, 'script.mjs')).href)
  if (typeof mod.default !== 'function') reply(2, { error: 'The builder must `export default` a function.' })
  const buf = await runExpert(mod.default, kit, assets)
  fs.writeFileSync(outFile, buf)
  const inspection = await inspect(buf)
  reply(0, { sha256: sha256(buf), bytes: buf.length, inspection, receipt: await checkExpert(buf, kit, inspection) })
} catch (e) {
  const msg = (e && e.message ? e.message : String(e)).replace(/\/[^\s'"]*\//g, '…/').slice(0, 400)
  reply(2, { error: `The builder failed: ${msg}` })
}
