/**
 * The `.dmind` bundle form (batch B5): a strict ZIP holding `manifest.json`, `document.json` and the
 * attachments under `assets/`. Bundles are written deterministically, so a given document and set of
 * files always produces the same bytes, in every implementation.
 */
import {
  ASSET_TYPES,
  MAX_ASSET_BYTES,
  MAX_ASSETS,
  allAttachments,
  assetPath,
  assetRef,
  cleanFileName,
  isAssetRef,
  sha256Hex,
  sniffType,
  type AssetStore,
  type AssetType,
  type Attachment,
} from './assets'
import { validateDiagram, type Diagram } from './dmind'
import { BUNDLE_LIMITS, ZipError, readZip, writeZip } from './zip'

export const BUNDLE_FORMAT = 'dmind-bundle/v1'
export const MAX_DOCUMENT_BYTES = 2_000_000

type ManifestAsset = { bytes: number; name: string; path: string; sha256: string; type: string }
type Manifest = {
  assets: ManifestAsset[]
  document: { bytes: number; path: string; sha256: string }
  format: string
}

const enc = new TextEncoder()
const dec = new TextDecoder('utf-8', { fatal: true })

/** Attachments the diagram refers to that are not in the store (they cannot be packed). */
export function missingAssets(d: Diagram, store: AssetStore): Attachment[] {
  return allAttachments(d).filter((a) => !store.has(a.asset))
}

export async function packBundle(d: Diagram, store: AssetStore): Promise<Uint8Array> {
  const valid = validateDiagram(d)
  const document = enc.encode(JSON.stringify(valid, null, 2) + '\n')
  if (document.length > MAX_DOCUMENT_BYTES) throw new ZipError('The document is too large to bundle.')
  const used = allAttachments(valid).filter((a) => store.has(a.asset))
  if (used.length > MAX_ASSETS) throw new ZipError(`A bundle can hold ${MAX_ASSETS} attachments.`)
  const files: { name: string; data: Uint8Array }[] = []
  const assets: ManifestAsset[] = []
  for (const a of [...used].sort((x, y) => (x.asset < y.asset ? -1 : 1))) {
    const data = store.get(a.asset)!
    if ((await sha256Hex(data.bytes)) !== a.asset.slice(7)) throw new ZipError('An attachment does not match its recorded hash.')
    const path = assetPath(a.asset, data.type)
    assets.push({ bytes: data.bytes.length, name: cleanFileName(data.name), path, sha256: a.asset.slice(7), type: data.type })
    files.push({ name: path, data: data.bytes })
  }
  const manifest: Manifest = {
    assets,
    document: { bytes: document.length, path: 'document.json', sha256: await sha256Hex(document) },
    format: BUNDLE_FORMAT,
  }
  return writeZip([
    { name: 'manifest.json', data: enc.encode(JSON.stringify(manifest, null, 2) + '\n') },
    { name: 'document.json', data: document },
    ...files,
  ])
}

export type Unpacked = { diagram: Diagram; assets: AssetStore; warnings: string[] }

export async function unpackBundle(bytes: Uint8Array): Promise<Unpacked> {
  const files = await readZip(bytes, BUNDLE_LIMITS)
  const manifestBytes = files.get('manifest.json')
  const documentBytes = files.get('document.json')
  if (!manifestBytes || !documentBytes) throw new ZipError('This archive is not a dmind bundle (manifest.json or document.json is missing).')
  let manifest: Manifest
  try {
    manifest = JSON.parse(dec.decode(manifestBytes))
  } catch {
    throw new ZipError('The bundle manifest is not valid.')
  }
  if (!manifest || manifest.format !== BUNDLE_FORMAT || !manifest.document || !Array.isArray(manifest.assets))
    throw new ZipError(`This bundle uses an unsupported format (expected ${BUNDLE_FORMAT}).`)
  if (documentBytes.length > MAX_DOCUMENT_BYTES) throw new ZipError('The bundle document is too large.')
  if (manifest.document.path !== 'document.json' || manifest.document.sha256 !== (await sha256Hex(documentBytes)) || manifest.document.bytes !== documentBytes.length)
    throw new ZipError('The bundle document does not match its manifest.')
  let doc: unknown
  try {
    doc = JSON.parse(dec.decode(documentBytes))
  } catch {
    throw new ZipError('The bundle document is not valid JSON.')
  }
  const diagram = validateDiagram(doc)
  if (manifest.assets.length > MAX_ASSETS) throw new ZipError(`A bundle can hold ${MAX_ASSETS} attachments.`)

  const store: AssetStore = new Map()
  const listed = new Set<string>(['manifest.json', 'document.json'])
  for (const a of manifest.assets) {
    if (!a || typeof a.path !== 'string' || typeof a.sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(a.sha256))
      throw new ZipError('The bundle manifest lists an invalid attachment.')
    const type = a.type as AssetType
    if (!ASSET_TYPES.includes(type)) throw new ZipError('The bundle contains an attachment type that is not allowed.')
    const ref = assetRef(a.sha256)
    if (a.path !== assetPath(ref, type)) throw new ZipError('The bundle manifest lists an unexpected attachment path.')
    const data = files.get(a.path)
    if (!data) throw new ZipError('The bundle is missing an attachment listed in its manifest.')
    listed.add(a.path)
    if (data.length > MAX_ASSET_BYTES || data.length !== a.bytes) throw new ZipError('A bundle attachment does not match its manifest.')
    if ((await sha256Hex(data)) !== a.sha256) throw new ZipError('A bundle attachment does not match its recorded hash.')
    if (sniffType(data, a.name) !== type) throw new ZipError('A bundle attachment is not the type it claims to be.')
    store.set(ref, { bytes: data, name: cleanFileName(String(a.name)), type })
  }
  for (const name of files.keys())
    if (!listed.has(name)) throw new ZipError(`The bundle contains an unlisted file (${name}) and was refused.`)
  const warnings: string[] = []
  const missing = allAttachments(diagram).filter((a) => !store.has(a.asset))
  if (missing.length) warnings.push(`${missing.length} attachment(s) are referenced but not included in the bundle.`)
  const stray = [...store.keys()].filter((ref) => !allAttachments(diagram).some((a) => a.asset === ref))
  if (stray.length) warnings.push(`${stray.length} included file(s) are not attached to any topic.`)
  return { diagram, assets: store, warnings }
}

export { isAssetRef }
