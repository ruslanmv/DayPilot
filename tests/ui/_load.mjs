/**
 * Loads the dependency-free TypeScript modules in packages/ui-bridge/src/diagrams for Node tests.
 * Each .ts file is transpiled to ESM in a temp directory (relative imports gain an .mjs suffix),
 * so modules can import each other exactly as the bundler sees them. React components (.tsx)
 * are not loaded; pure logic stays in .ts files for this reason.
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const root = new URL('../../packages/ui-bridge/', import.meta.url)
const require = createRequire(root)
const ts = require('typescript')
const sourceDir = new URL('src/diagrams/', root)

let cached
export async function loadDiagramModules() {
  if (cached) return cached
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'dmind-mods-'))
  // Pure modules only: anything importing from outside this folder (network layer) is skipped.
  const names = fs
    .readdirSync(sourceDir)
    .filter((f) => f.endsWith('.ts') && !f.endsWith('.d.ts'))
    .filter((f) => !/from\s+['"]\.\.\//.test(fs.readFileSync(new URL(f, sourceDir), 'utf8')))
  for (const file of names) {
    const code = ts.transpileModule(fs.readFileSync(new URL(file, sourceDir), 'utf8'), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
      fileName: file,
    }).outputText.replace(/(from\s+['"])(\.\/[\w-]+)(['"])/g, '$1$2.mjs$3')
    fs.writeFileSync(path.join(out, file.replace(/\.ts$/, '.mjs')), code)
  }
  const modules = {}
  for (const file of names) {
    const name = file.replace(/\.ts$/, '')
    modules[name] = await import(pathToFileURL(path.join(out, name + '.mjs')).href)
  }
  cached = modules
  return modules
}
