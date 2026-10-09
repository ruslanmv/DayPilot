/** Portrait URLs must use the same gateway base as JSON API requests. */
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../../packages/ui-bridge/package.json', import.meta.url))
const ts = require('typescript')
const source = fs.readFileSync(
  new URL('../../packages/ui-bridge/src/agents/portraitUrl.ts', import.meta.url), 'utf8',
)
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext },
}).outputText
const { portraitUrl } = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))

const avatar = '/v1/agents/profiles/agent-1/avatar?workspaceId=crew+%26+planning'
const cases = [
  [avatar, '/api', '/api' + avatar],
  [avatar, '/api/', '/api' + avatar],
  [avatar, '', avatar],
  [avatar, '/daypilot/api', '/daypilot/api' + avatar],
  [avatar, 'https://gateway.example.test/api/', 'https://gateway.example.test/api' + avatar],
  ['/api' + avatar, '/api', '/api' + avatar],
  ['https://gateway.example.test' + avatar, '/api', 'https://gateway.example.test' + avatar],
  ['data:image/png;base64,iVBORw0KGgo=', '/api', 'data:image/png;base64,iVBORw0KGgo='],
  [null, '/api', undefined],
  [undefined, '/api', undefined],
  ['', '/api', undefined],
]
for (const [url, base, expected] of cases) assert.equal(portraitUrl(url, base), expected)
console.log(`Agent portrait URLs: ${cases.length} checks passed`)
