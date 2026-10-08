/**
 * Structural inspection of an exported .pptx: what is actually inside the file (not what we meant
 * to write). Used by the quality gate to prove native objects, notes and slide count.
 */
import JSZip from 'jszip'

export async function inspect(buf) {
  const zip = await JSZip.loadAsync(buf)
  const names = Object.keys(zip.files)
  const slideFiles = names.filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a, b) => num(a) - num(b))
  const slides = []
  for (const f of slideFiles) {
    const xml = await zip.file(f).async('string')
    const rels = (await zip.file(f.replace('slides/', 'slides/_rels/') + '.rels')?.async('string')) ?? ''
    const chartParts = [...rels.matchAll(/Target="(?:\.\.|\/ppt)\/charts\/(chart\d+\.xml)"/g)].map((m) => m[1])
    const charts = []
    for (const c of chartParts) {
      const cx = await zip.file(`ppt/charts/${c}`).async('string')
      charts.push({ part: c, series: (cx.match(/<c:ser>/g) ?? []).length, points: [...cx.matchAll(/<c:v>([^<]*)<\/c:v>/g)].length })
    }
    const notesPart = (rels.match(/Target="\.\.\/notesSlides\/(notesSlide\d+\.xml)"/) ?? [])[1]
    const notes = notesPart ? textOf(await zip.file(`ppt/notesSlides/${notesPart}`).async('string')) : ''
    slides.push({
      part: f,
      names: [...xml.matchAll(/<p:cNvPr id="\d+" name="([^"]*)"/g)].map((m) => m[1]),
      textBoxes: (xml.match(/txBox="1"/g) ?? []).length,
      tables: (xml.match(/<a:tbl>/g) ?? []).length,
      charts,
      pictures: (xml.match(/<p:pic>/g) ?? []).length,
      shapes: (xml.match(/<p:sp>/g) ?? []).length,
      altTexts: [...xml.matchAll(/descr="([^"]*)"/g)].map((m) => m[1]).filter(Boolean).length,
      text: textOf(xml),
      notes,
    })
  }
  const theme = (await zip.file('ppt/theme/theme1.xml')?.async('string')) ?? ''
  return {
    slides,
    themeColors: Object.fromEntries([...theme.matchAll(/<a:(dk1|lt1|dk2|lt2|accent\d|hlink|folHlink)><a:srgbClr val="([0-9A-F]{6})"/g)].map((m) => [m[1], m[2]])),
    fonts: [...new Set([...theme.matchAll(/<a:latin typeface="([^"]+)"/g)].map((m) => m[1]))],
    hasMacros: names.some((n) => /vbaProject|\.bin$/.test(n) && !n.includes('embeddings')),
    externalLinks: names.filter((n) => n.endsWith('.rels')).length ? await externals(zip, names) : 0,
  }
}
const num = (f) => Number(f.match(/(\d+)\.xml$/)[1])
function textOf(xml) {
  return [...xml.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map((m) => m[1].replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'")).join(' ')
}
async function externals(zip, names) {
  let n = 0
  for (const r of names.filter((x) => x.endsWith('.rels'))) n += ((await zip.file(r).async('string')).match(/TargetMode="External"/g) ?? []).length
  return n
}
