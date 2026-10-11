/**
 * 鼠标指针样式（颜色 + 图形 + 高亮光晕）生成器。
 *
 * 为什么不写在 index.css 里手写：**指针的 SVG 是独立文档，读不到 CSS 变量**
 * （`var(--app-brand)` 在 cursor 的 data URL 里不会生效）。所以只能"每套皮肤
 * 各生成一份" —— 色值从 index.css 里现读，皮肤一改这里自动跟着变。
 *
 * 产出：src/renderer/cursors.css（由 main.tsx 在 index.css 之后引入）
 *
 * 图形与配色口径（产品定稿）：
 *   - **日间皮肤：白色核心 + 主色光晕**；**夜间皮肤：主色核心 + 白色光晕**。
 *     共同点：核心与光晕**一深一浅对着来**，且始终有近黑描边把核心从浅底里切出来
 *     —— 这才是"任何背景上都找得到指针"的关键；品牌色只出现在核心或光晕其中的一处，
 *     所以仍看得出是哪套皮肤。
 *     （改之前是"品牌色填充 + 细描边"，在同色系界面上会糊在一起，用户找不到指针；
 *       只做成"白核心 + 主色光晕"也不行 —— 夜间底会把白核心淹没。）
 *   - 形状照系统原生（箭头 / 手型 / I 形 / ⇔ / 禁止），不自己发明形状。
 *   - 光晕用**三层递减的半透明描边**叠出来，**不用 SVG 滤镜**：cursor 是静态
 *     光栅化，滤镜在部分环境下会直接不渲染，叠描边是稳的。
 *   - 「禁止」的圆环与光晕取该皮肤的危险色（语义色），核心仍是白色。
 *   - 画布 32×32（图形本体仍是原来的 24 大小，四周留 4px 给光晕）；
 *     热点随平移量同步 +4，不然点击点会偏。
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const INDEX_CSS = path.join(ROOT, 'src', 'index.css')
const OUT_CSS = path.join(ROOT, 'src', 'cursors.css')

/** 画布尺寸；图形本体按 24 设计，四周留 7px 给光晕（光晕最宽 13.5 → 单边 6.75） */
const S = 38
const PAD = 7

/** 核心与描边（固定色，不跟皮肤 —— 这才保证"任何背景都跳得出来"） */
const CORE = '#ffffff'
const OUTLINE = '#12161f'

// --------------------------------------------------------------------------
// 1. 从 index.css 读每套皮肤的色值
// --------------------------------------------------------------------------
function readSkins(css) {
  const skins = {}
  const pluck = (block, name) => {
    const m = block.match(new RegExp(`${name}\\s*:\\s*([^;]+);`))
    return m ? m[1].trim() : null
  }
  // ⚠️ 选择器里可能还跟着别的（本项目的夜间皮肤是 `[data-theme='dark'],\n.dark {`），
  // 所以 `]` 到 `{` 之间一律放宽 —— 严格匹配会**整套皮肤静默漏掉**。
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

/** 画布色是不是深色：决定核心/光晕谁用白、谁用主色 */
function isDarkHex(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return false
  const n = parseInt(m[1], 16)
  const l = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255
  return l < 0.5
}

// --------------------------------------------------------------------------
// 2. 图形（形状照系统原生；白核心 + 深描边 + 三层光晕）
// --------------------------------------------------------------------------

/**
 * 四层递减的半透明描边 = 一圈由内向外淡出的光晕。
 *
 * 层数从 3 加到 4、宽度整体放大（最外 13.5，单边 6.75）：3 层时"范围太小"，
 * 光晕看着像一条贴着图形的细边，而不是发光。
 * `bright` 是亮度倍率（夜间用白晕，要更亮才压得住深底）。
 */
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

/** 包一层画布：图形整体平移 PAD，四周留给光晕 */
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

/** 禁止：圆环 + 斜杠（危险色语义），核心跟日/夜规则走 */
const CIRCLE_D = 'M4.9 12a7.1 7.1 0 1 0 14.2 0 7.1 7.1 0 1 0-14.2 0'
const notAllowed = (p) =>
  svg(`
  ${glow(CIRCLE_D, p.glow, 0.9 * p.gs, p.bright)}
  <circle cx="12" cy="12" r="7.1" fill="${p.core}" stroke="${p.accent}" stroke-width="2"/>
  <path d="M7.2 16.8 16.8 7.2" stroke="${p.accent}" stroke-width="2" stroke-linecap="round"/>`)

const toUrl = (svgText) =>
  `url("data:image/svg+xml,${encodeURIComponent(svgText.replace(/\s+/g, ' ').trim())}")`

/** 每个指针：形状函数 + 热点（热点 = 原 24 坐标系 + PAD） */
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

// --------------------------------------------------------------------------
// 3. 写 CSS
// --------------------------------------------------------------------------
const css = fs.readFileSync(INDEX_CSS, 'utf8')
const skins = readSkins(css)
const ids = Object.keys(skins)
if (ids.length < 10) {
  console.error(`只从 index.css 里读到了 ${ids.length} 套皮肤，色值解析可能失效了，先别生成。`)
  process.exit(1)
}

/**
 * 每套皮肤 × 每个指针的配色（产品定稿的日/夜规则）：
 *
 *   日间皮肤：**白色核心 + 主色光晕** —— 白核心在浅底上最跳
 *   夜间皮肤：**主色核心 + 白色光晕** —— 夜间底会把白核心淹没，反过来才跳
 *
 * 描边始终近黑：不管白天黑夜，它负责把核心从"浅色背景"里切出来。
 * 「禁止」的圆环/斜杠：日间用危险色（一眼看出是禁止），夜间用近黑
 * （因为夜间那版的**核心本身就是危险色**，圆环再用同色就糊成一坨）。
 */
function paletteFor(skin, key) {
  const semantic = key === 'not-allowed' ? skin.danger : skin.brand
  if (!skin.dark) {
    // 日间：白核心 + 主色光晕（亮度基准 1，范围基准 1）
    return { core: CORE, outline: OUTLINE, accent: semantic, glow: semantic, bright: 1, gs: 1 }
  }
  // 夜间：主色核心 + 白色光晕。白晕要**更亮更大**才压得住深底
  // （「夜间的光晕不够亮」）—— 亮度 ×1.4、范围 ×1.08。
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

// --------------------------------------------------------------------------
// 4. 预览页（--preview）：把指针放在**同色系底**上验辨识度
// --------------------------------------------------------------------------
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
      // 四块底：品牌色 20% 浅混（最像"同色系界面"）、品牌色实心、近黑、纯白
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
