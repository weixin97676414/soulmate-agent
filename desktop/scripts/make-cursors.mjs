






















import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const INDEX_CSS = path.join(ROOT, 'src', 'index.css')
const OUT_CSS = path.join(ROOT, 'src', 'cursors.css')


const S = 38
const PAD = 7


const CORE = '#ffffff'
const OUTLINE = '#12161f'




function readSkins(css) {
  const skins = {}
  const pluck = (block, name) => {
    const m = block.match(new RegExp(`${name}\\s*:\\s*([^;]+);`))
    return m ? m[1].trim() : null
  }
  
  
  const re = /\[data-theme='([a-z]+)'\][^{]*\{([\s\S]*?)\n\}/g
  let m
  while ((m = re.exec(css))) {
    const [, id, block] = m
    const brand = pluck(block, '--app-brand')
    const ink = pluck(block, '--app-ink')
    const canvas = pluck(block, '--app-canvas-solid')
    const danger = pluck(block, '--app-danger')
    if (brand && ink && canvas) {
      skins[id] = { brand, ink, canvas, danger: danger ?? '#e5484d', dark: isDarkHex(canvas) }
    }
  }
  return skins
}


function isDarkHex(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return false
  const n = parseInt(m[1], 16)
  const l = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
  return l < 0.5
}












const GLOW_LAYERS = [
  { w: 13.5, o: 0.14 },
  { w: 9.5, o: 0.24 },
  { w: 6, o: 0.42 },
  { w: 3.4, o: 0.68 }
]
const glow = (d, color, scale = 1, bright = 1) =>
  GLOW_LAYERS.map(
    (l) =>
      `<path d="${d}" fill="none" stroke="${color}" stroke-opacity="${Math.min(1, l.o * bright).toFixed(3)}" stroke-width="${(l.w * scale).toFixed(2)}" stroke-linejoin="round" stroke-linecap="round"/>`
  ).join('\n  ')


const svg = (inner) => `
<svg xmlns="http://www.w3.org/2000/svg" width="${S}" height="${S}" viewBox="0 0 ${S} ${S}">
  <g transform="translate(${PAD},${PAD})">${inner}
  </g>
</svg>`

const ARROW_D = 'M5.2 2.2 5.2 19.6 9.5 15.5 12.3 21.8 15.4 20.4 12.6 14.2 18.6 14Z'
const arrow = (p) =>
  svg(`
  ${glow(ARROW_D, p.glow, p.gs, p.bright)}
  <path d="${ARROW_D}" fill="${p.core}" stroke="${p.outline}" stroke-width="1.7" stroke-linejoin="round"/>`)

const HAND_D =
  'M10.4 3.1c1 0 1.85.8 1.85 1.85v5.55h1.2V6.3c0-1 .8-1.85 1.85-1.85s1.85.8 1.85 1.85v4.2h1.2V8.1c0-1 .8-1.85 1.85-1.85s1.85.8 1.85 1.85v5.6c0 3.95-2.5 6.75-6.5 6.75h-1.6c-1.95 0-3.3-.9-4.2-2.6l-2.5-4.6c-.45-.9-.1-1.95.8-2.4.85-.4 1.85-.1 2.35.7l1.1 1.75V4.95c0-1.05.85-1.85 1.85-1.85Z'
const pointer = (p) =>
  svg(`
  ${glow(HAND_D, p.glow, p.gs, p.bright)}
  <path d="${HAND_D}" fill="${p.core}" stroke="${p.outline}" stroke-width="1.6" stroke-linejoin="round"/>`)

const TEXT_D = 'M6.4 4.4h11.2v2.4h-4.3v10.4h4.3v2.4H6.4v-2.4h4.3V6.8H6.4Z'
const text = (p) =>
  svg(`
  ${glow(TEXT_D, p.glow, 0.62 * p.gs, p.bright)}
  <path d="${TEXT_D}" fill="${p.core}" stroke="${p.outline}" stroke-width="1.2" stroke-linejoin="round"/>`)

const RESIZE_D = 'M2.6 12 8 7.4v2.9h8V7.4L21.4 12 16 16.6v-2.9H8v2.9Z'
const colResize = (p) =>
  svg(`
  ${glow(RESIZE_D, p.glow, 0.8 * p.gs, p.bright)}
  <path d="${RESIZE_D}" fill="${p.core}" stroke="${p.outline}" stroke-width="1.5" stroke-linejoin="round"/>`)


const CIRCLE_D = 'M4.9 12a7.1 7.1 0 1 0 14.2 0 7.1 7.1 0 1 0-14.2 0'
const notAllowed = (p) =>
  svg(`
  ${glow(CIRCLE_D, p.glow, 0.9 * p.gs, p.bright)}
  <circle cx="12" cy="12" r="7.1" fill="${p.core}" stroke="${p.accent}" stroke-width="2"/>
  <path d="M7.2 16.8 16.8 7.2" stroke="${p.accent}" stroke-width="2" stroke-linecap="round"/>`)

const toUrl = (svgText) =>
  `url("data:image/svg+xml,${encodeURIComponent(svgText.replace(/\s+/g, ' ').trim())}")`


const CURSORS = [
  {
    key: 'default',
    prop: '--cur-default',
    shape: arrow,
    hotspot: `${5.2 + PAD} ${2.2 + PAD}`,
    fallback: 'default'
  },
  {
    key: 'pointer',
    prop: '--cur-pointer',
    shape: pointer,
    hotspot: `${10 + PAD} ${3 + PAD}`,
    fallback: 'pointer'
  },
  {
    key: 'text',
    prop: '--cur-text',
    shape: text,
    hotspot: `${12 + PAD} ${12 + PAD}`,
    fallback: 'text'
  },
  {
    key: 'col-resize',
    prop: '--cur-col-resize',
    shape: colResize,
    hotspot: `${12 + PAD} ${12 + PAD}`,
    fallback: 'col-resize'
  },
  {
    key: 'not-allowed',
    prop: '--cur-not-allowed',
    shape: notAllowed,
    hotspot: `${12 + PAD} ${12 + PAD}`,
    fallback: 'not-allowed'
  }
]




const css = fs.readFileSync(INDEX_CSS, 'utf8')
const skins = readSkins(css)
const ids = Object.keys(skins)
if (ids.length < 10) {
  console.error(`只从 index.css 里读到了 ${ids.length} 套皮肤，色值解析可能失效了，先别生成。`)
  process.exit(1)
}











function paletteFor(skin, key) {
  const semantic = key === 'not-allowed' ? skin.danger : skin.brand
  if (!skin.dark) {
    
    return { core: CORE, outline: OUTLINE, accent: semantic, glow: semantic, bright: 1, gs: 1 }
  }
  
  
  return {
    core: semantic,
    outline: OUTLINE,
    accent: key === 'not-allowed' ? OUTLINE : semantic,
    glow: '#ffffff',
    bright: 1.4,
    gs: 1.08
  }
}

const varBlocks = ids
  .map((id) => {
    const skin = skins[id]
    const kind = skin.dark ? '夜间' : '日间'
    const desc = skin.dark
      ? `主色 ${skin.brand} 核心 + 白色光晕`
      : `白色核心 + 主色 ${skin.brand} 光晕`
    const lines = CURSORS.map(
      (c) => `  ${c.prop}: ${toUrl(c.shape(paletteFor(skin, c.key)))} ${c.hotspot};`
    )
    return `/* ${id}（${kind}：${desc}） */\n[data-theme='${id}'] {\n${lines.join('\n')}\n}`
  })
  .join('\n\n')

const heads = `/* ==================================================================
 * 鼠标指针样式（白核心 + 深描边 + 品牌色光晕）—— **自动生成，不要手改**
 *   生成器：scripts/make-cursors.mjs（npm run make-cursors）
 *   色值来源：src/renderer/index.css 里各皮肤的 --app-brand / --app-danger
 *
 * 为什么核心是白的：系统原生指针就是"白填充 + 黑描边"，任何背景都不会融；
 * 品牌色只出现在外围光晕上，所以仍能看出是哪套皮肤。
 * 光晕 = 三层递减的半透明描边（不用 SVG 滤镜，cursor 是静态光栅化，滤镜不可靠）。
 * 画布 32×32，图形本体 24，四周 4px 留给光晕；热点已按 +4 平移。
 * ================================================================== */

${varBlocks}

/* ---- 应用到各区域（与 index.css 的语义口径一致） ---------------- */
html {
  cursor: var(--cur-default), default;
}
button:not(:disabled),
[role='button']:not([aria-disabled='true']),
a[href],
summary,
label[for],
select:not(:disabled),
input[type='checkbox']:not(:disabled),
input[type='radio']:not(:disabled),
input[type='color']:not(:disabled),
input[type='file']:not(:disabled),
.cursor-pointer,
.cm-editor .cm-gutters,
.vditor-toolbar,
.vditor-toolbar__item,
.vditor-toolbar__item svg,
.vditor-panel,
.vditor-hint button,
.vditor-breadcrumb__item {
  cursor: var(--cur-pointer), pointer;
}
:disabled,
[aria-disabled='true'],
.cursor-not-allowed {
  cursor: var(--cur-not-allowed), not-allowed;
}
input:not([type='checkbox']):not([type='radio']):not([type='file']),
textarea,
[contenteditable='true'],
.vditor-reset,
.vditor-sv,
.vditor-wysiwyg,
.cm-editor .cm-content,
.cursor-text {
  cursor: var(--cur-text), text;
}
.cursor-col-resize,
.cm-editor .cm-gutters.cm-gutters-before {
  cursor: var(--cur-col-resize), col-resize;
}
`

fs.writeFileSync(OUT_CSS, heads)
console.log(
  `已生成 src/renderer/cursors.css：${ids.length} 套皮肤 × ${CURSORS.length} 个指针（白核心 + 深描边 + 光晕）\n` +
    `  皮肤：${ids.join('、')}`
)




if (process.argv.includes('--preview')) {
  const hexToRgb = (hex) => {
    const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
    if (!m) return [0, 0, 0]
    const n = parseInt(m[1], 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
  }
  const mix = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t))
  const rgb = (c) => `rgb(${c[0]} ${c[1]} ${c[2]})`

  const rows = ids
    .map((id) => {
      const skin = skins[id]
      const brand = hexToRgb(skin.brand)
      const canvas = hexToRgb(skin.canvas)
      
      const grounds = [
        { name: '品牌20%', bg: rgb(mix([255, 255, 255], brand, 0.2)) },
        { name: '品牌实心', bg: rgb(brand) },
        { name: '近黑', bg: '#111318' },
        { name: '纯白', bg: '#ffffff' },
        { name: '画布色', bg: rgb(canvas) }
      ]
      const cells = grounds
        .map((g) => {
          const imgs = CURSORS.map(
            (c) =>
              `<img src="${toUrl(c.shape(paletteFor(skin, c.key))).slice(5, -1)}" width="64" height="64">`
          ).join('')
          return `<div class="cell" style="background:${g.bg}"><span>${g.name}</span><div>${imgs}</div></div>`
        })
        .join('')
      return `<div class="row"><b>${id}</b><div class="cells">${cells}</div></div>`
    })
    .join('\n')

  const html = `<!doctype html><meta charset="utf-8"><style>
body{font:12px system-ui;background:#6b7280;padding:10px;margin:0}
.row{display:flex;gap:10px;margin-bottom:8px}
b{width:96px;color:#fff;padding-top:24px}
.cells{display:flex;gap:6px}
.cell{padding:2px 6px 4px;border-radius:8px;text-align:center}
.cell span{color:#ffffffaa;font-size:10px}
.cell img{display:block}
</style>${rows}`
  const previewPath = path.join(process.env.TEMP ?? '/tmp', 'cursor-preview.html')
  fs.writeFileSync(previewPath, html)
  console.log(`预览页：${previewPath}`)
}
