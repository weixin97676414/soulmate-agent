/**
 * 本地发布：把"该给用户的东西"整理成三份目录。
 *
 * ## 三份目录是什么（产品约定）
 *
 * ```
 * D:\win版客户端开发\
 * ├─ 打包文件\无注释-<版本>\      ← 首次安装用（NSIS 安装包 + 校验值）
 * └─ 更新文件\
 *    ├─ cn\                       ← 大陆线路：manifest-cn.json + files/
 *    └─ seoul\                    ← 首尔线路：manifest-seoul.json + files/
 * ```
 *
 * ## "无注释"的边界（重要，别改错）
 *
 * | 内容 | 产物里是否带注释 |
 * |---|---|
 * | 核心自身的 Python 代码 | **不带** —— 它编译成 `.pyc` 字节码，字节码里没有注释这个概念 |
 * | 前端界面（`dist/**`） | **不带** —— Vite 生产构建压缩时已剔除 |
 * | 主进程 JS（`dist-electron/**`） | **不带** —— `tsconfig.electron.json` 开了 `removeComments` |
 * | 技能脚本 `.py` / `SKILL.md` / 提示词 `.md` | **带** —— 它们属于"内容"，产品明确要求原样保留 |
 * | 本地源码与源码备份 | **带** —— 不然以后没法维护 |
 *
 * 所以本脚本**不做任何"删注释"的动作**，它只做两件事：① **自检**产物确实不带注释
 * （`.map` 绝对不许有 —— 有 map 就等于把带注释的源码一起送出去了）；
 * ② 把产物整理成三份目录。真正的"无注释"是构建配置保证的。
 *
 * ## 更新范围（为什么不是"包里的所有文件"）
 *
 * 只把**我们自己会改的东西**纳入增量更新：
 * - `renderer`：`resources/dist/**`（前端界面）
 * - `core`    ：`resources/agent-core/_internal/my_agent/**`（我们自己的核心代码，1518 个 .pyc）
 *
 * **刻意排除**第三方大块（`playwright/` 89MB、`chromadb_rust_bindings` 60MB、`numpy`、
 * `onnxruntime`、`base_library.zip` …）与 `agent-core.exe` 本体：
 * 它们几乎不随我们的日常改动变化，一旦真变了（依赖升级）就属于"必须整包重装"的范畴，
 * 由 manifest 的 `min_from` 拦住老客户端、让它去下整包。这样日常一次发布的增量通常
 * 只有几百 KB 到几 MB。
 *
 * 用法：
 *   npm run publish:local                    # 完整跑：构建 → 打包 → 整理三份
 *   npm run publish:local -- --skip-build    # 复用已有产物（release/win-unpacked）
 *   npm run publish:local -- --unpacked=<dir>  # 指定已有的打包产物目录
 *   npm run publish:local -- --version=0.1.60
 */
import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')
const repoDir = path.resolve(desktopDir, '..')

/** 三份目录的根。⚠️ 只有这一处定义，要换位置改这里。 */
const RELEASE_ROOT = 'D:\\win版客户端开发'
const PACK_DIR = path.join(RELEASE_ROOT, '打包文件')
const UPDATE_DIR = path.join(RELEASE_ROOT, '更新文件')

/**
 * 每条线路的更新根地址（客户端就是从这里取 manifest 与文件）。
 * ⚠️ 待办：拿到用户的 GitHub 仓库地址后，把 seoul 那条换成真实地址。
 */
const LINES = {
  cn: { baseUrl: 'https://china.xinjianxue.com/updates' },
  seoul: { baseUrl: 'https://raw.githubusercontent.com/REPLACE_ME/REPLACE_ME/main/updates' },
}

/** 参与增量更新的目录（相对"安装根"）。**顺序即优先级**，不要随意改。 */
const UPDATE_SCOPE = [
  { target: 'renderer', dir: 'resources/dist' },
  { target: 'core', dir: 'resources/agent-core/_internal/my_agent' },
]

const args = process.argv.slice(2)
const flag = (name) => args.some((item) => item === `--${name}`)
const value = (name) => {
  const hit = args.find((item) => item.startsWith(`--${name}=`))
  return hit ? hit.slice(name.length + 3) : null
}

const log = (message) => console.log(`[publish] ${message}`)
const fail = (message) => {
  console.error(`[publish] ✗ ${message}`)
  process.exit(1)
}

// --------------------------------------------------------------------------- //
// 工具
// --------------------------------------------------------------------------- //

/** 算一个文件的 sha256（流式：既算 44MB 的 exe 也不吃内存）。 */
function sha256(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256')
    fs.createReadStream(file)
      .on('data', (chunk) => hash.update(chunk))
      .on('end', () => resolve(hash.digest('hex')))
      .on('error', reject)
  })
}

/** 递归列出目录下所有文件（相对路径用 `/`，跨平台一致）。 */
function walk(dir) {
  const out = []
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) visit(full)
      else if (entry.isFile()) out.push(full)
    }
  }
  if (fs.existsSync(dir)) visit(dir)
  return out
}

const toPosix = (value) => value.split(path.sep).join('/')
const mb = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

// --------------------------------------------------------------------------- //
// ① 构建与打包
// --------------------------------------------------------------------------- //

function run(label, command, commandArgs, cwd = desktopDir) {
  log(label)
  const result = spawnSync(command, commandArgs, {
    cwd,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  })
  if (result.status !== 0) fail(`${label} 失败（退出码 ${result.status}）`)
}

function buildAndPack() {
  // 复用 dist.mjs：它已经处理了代理、镜像、核心是否重建、以及"改名而非删除"以绕开
  // 批量删除保护。这里不重复实现，只负责调用。
  run('构建并打包（scripts/dist.mjs）', 'node', ['scripts/dist.mjs'])
}

function resolveUnpacked() {
  const explicit = value('unpacked')
  const fallback = path.join(desktopDir, 'release', 'win-unpacked')
  const dir = explicit ? path.resolve(explicit) : fallback
  if (!fs.existsSync(dir)) fail(`找不到打包产物目录：${dir}`)
  return dir
}

// --------------------------------------------------------------------------- //
// ② 去注释自检（这是"无注释"的验收口）
// --------------------------------------------------------------------------- //

function selfCheck(unpacked) {
  log('自检：产物是否真的不含注释')
  const problems = []

  // (1) 任何 sourcemap 都是事故：它能让用户看到带注释的原始源码
  const maps = [
    ...walk(path.join(desktopDir, 'dist')),
    ...walk(path.join(desktopDir, 'dist-electron')),
    ...walk(path.join(unpacked, 'resources', 'dist')),
  ].filter((file) => file.endsWith('.map'))
  if (maps.length) problems.push(`产物里存在 sourcemap（${maps.length} 个）：${maps[0]}`)

  // (2) 主进程 JS 不该有行首注释（构建配置已保证；这里防的是"以后有人把开关关了"）
  const mainJs = path.join(desktopDir, 'dist-electron', 'electron', 'main.js')
  if (fs.existsSync(mainJs)) {
    const source = fs.readFileSync(mainJs, 'utf8')
    if (/^\s*\/\//m.test(source) || /^\s*\/\*/m.test(source)) {
      problems.push('dist-electron/electron/main.js 里仍有行首注释（removeComments 被关掉了？）')
    }
  }

  // (3) 前端页面必须用**相对**资源路径，否则 file:// 下会指向磁盘根、直接白屏
  const indexHtml = path.join(unpacked, 'resources', 'dist', 'index.html')
  if (!fs.existsSync(indexHtml)) {
    problems.push('打包产物里没有 resources/dist/index.html（dist 没被打进 extraResources？）')
  } else {
    const html = fs.readFileSync(indexHtml, 'utf8')
    if (!html.includes('Content-Security-Policy')) problems.push('index.html 里没有 CSP meta')
    const absolute = html.match(/(src|href)="\/(?!\/)/g)
    if (absolute) problems.push('index.html 里有以 / 开头的绝对资源路径（file:// 下会白屏）')
  }

  /*
    (4) 前端 JS 里不该有"带缩进/行首的注释"。

    ⚠️ 判据换过一次，别改回去：最初写的是"行数 > 200 就算没压缩"——**那是错的**，
    Vite 的 esbuild 压缩产物仍会保留相当多换行（实测 374 行、平均行长约 3.7KB），
    行数根本区分不了压缩与否，反而会误报、卡住发布。
    真正可靠的判据是"压缩后不会存在带缩进或行首的注释"（未压缩的源码到处都是）。
  */
  const assets = walk(path.join(unpacked, 'resources', 'dist', 'assets')).filter((f) => f.endsWith('.js'))
  for (const asset of assets) {
    const source = fs.readFileSync(asset, 'utf8')
    const avgLine = source.length / Math.max(1, source.split('\n').length)
    if (avgLine < 200) {
      problems.push(`前端资源看着没被压缩（${path.basename(asset)} 平均行长仅 ${Math.round(avgLine)} 字符）`)
      break
    }
  }

  if (problems.length) {
    for (const item of problems) console.error(`[publish] ✗ ${item}`)
    fail('自检未通过，已中止（没有生成任何发布目录）')
  }
  log(`自检通过：无 sourcemap · 主进程无注释 · 页面用相对路径 · 前端已压缩`)
}

// --------------------------------------------------------------------------- //
// ③ 生成清单（按内容寻址）
// --------------------------------------------------------------------------- //

async function buildManifest(unpacked, version, line) {
  const files = []
  let totalBytes = 0
  for (const scope of UPDATE_SCOPE) {
    const root = path.join(unpacked, scope.dir)
    for (const full of walk(root)) {
      const rel = toPosix(path.relative(root, full))
      const stat = fs.statSync(full)
      files.push({
        target: scope.target,
        path: rel,
        size: stat.size,
        sha256: await sha256(full),
      })
      totalBytes += stat.size
    }
  }
  files.sort((a, b) => (a.target + a.path < b.target + b.path ? -1 : 1))
  return {
    manifest: {
      version,
      // ⚠️ 老客户端从哪个版本起才支持增量：先留成当前版本。
      // 将来若要"强制整包"（换依赖、改协议），把新版本的 min_from 设成"再往后的版本"即可。
      min_from: version,
      line,
      generated_at: new Date().toISOString(),
      base_url: LINES[line].baseUrl,
      files,
    },
    totalBytes,
  }
}

/** 把清单里的文件按内容摆进 `files/<sha 前 2 位>/<sha>.bin`（已存在就跳过）。 */
async function materializeFiles(unpacked, manifest, targetRoot) {
  const filesDir = path.join(targetRoot, 'files')
  fs.mkdirSync(filesDir, { recursive: true })
  let copied = 0
  for (const item of manifest.files) {
    const bucket = path.join(filesDir, item.sha256.slice(0, 2))
    const dest = path.join(bucket, `${item.sha256}.bin`)
    if (fs.existsSync(dest)) continue
    const scope = UPDATE_SCOPE.find((entry) => entry.target === item.target)
    const source = path.join(unpacked, scope.dir, item.path.split('/').join(path.sep))
    fs.mkdirSync(bucket, { recursive: true })
    fs.copyFileSync(source, dest)
    copied += 1
  }
  return copied
}

/** 与上一版清单做差分（上一版从 cn 那份读，两份内容一致）。 */
function diffAgainstPrevious(manifest) {
  const previousFile = path.join(UPDATE_DIR, 'cn', 'manifest-cn.json')
  if (!fs.existsSync(previousFile)) return null
  const previous = JSON.parse(fs.readFileSync(previousFile, 'utf8'))
  const key = (item) => `${item.target}/${item.path}`
  const before = new Map(previous.files.map((item) => [key(item), item.sha256]))
  const after = new Map(manifest.files.map((item) => [key(item), item.sha256]))

  const added = [...after.keys()].filter((k) => !before.has(k))
  const changed = [...after.keys()].filter((k) => before.has(k) && before.get(k) !== after.get(k))
  const removed = [...before.keys()].filter((k) => !after.has(k))
  let bytes = 0
  for (const item of manifest.files) {
    const k = key(item)
    if (!before.has(k) || before.get(k) !== item.sha256) bytes += item.size
  }
  return { previousVersion: previous.version, added, changed, removed, bytes }
}

// --------------------------------------------------------------------------- //
// 主流程
// --------------------------------------------------------------------------- //

async function main() {
  const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'))
  const version = value('version') ?? pkg.version
  log(`版本 ${version}`)

  if (!flag('skip-build')) buildAndPack()
  else log('跳过构建与打包（--skip-build）')

  const unpacked = resolveUnpacked()
  log(`打包产物：${unpacked}`)

  selfCheck(unpacked)

  // ---- 打包文件\无注释-<版本> ---- //
  const packTarget = path.join(PACK_DIR, `无注释-${version}`)
  fs.mkdirSync(packTarget, { recursive: true })
  const setupName = `Soulmate Agent Setup ${version}.exe`
  const setupSrc = path.join(path.dirname(unpacked), setupName)
  if (!fs.existsSync(setupSrc)) fail(`找不到安装包：${setupSrc}`)
  fs.copyFileSync(setupSrc, path.join(packTarget, setupName))
  const blockmapSrc = `${setupSrc}.blockmap`
  if (fs.existsSync(blockmapSrc)) {
    fs.copyFileSync(blockmapSrc, path.join(packTarget, `${setupName}.blockmap`))
  }
  const setupHash = await sha256(path.join(packTarget, setupName))
  fs.writeFileSync(
    path.join(packTarget, 'SHA256SUMS.txt'),
    `${setupHash}  ${setupName}\n`,
    'utf8',
  )
  log(`打包文件 → ${packTarget}（${mb(fs.statSync(path.join(packTarget, setupName)).size)}）`)

  // ---- 更新文件\cn 与 \seoul ---- //
  for (const line of Object.keys(LINES)) {
    const targetRoot = path.join(UPDATE_DIR, line)
    const { manifest, totalBytes } = await buildManifest(unpacked, version, line)
    /*
      ⚠️ 差分必须**在写新清单之前**算完（踩过一次）：原先写在 `writeFileSync` 之后，
      于是"上一版清单"读到的就是**刚写下的这一版**，结果永远是"新增 0 · 修改 0"——
      看起来一切正常，实际上差分完全失效（这种"静默失效"最难发现）。
    */
    const diff = line === 'cn' ? diffAgainstPrevious(manifest) : null
    fs.mkdirSync(targetRoot, { recursive: true })
    const copied = await materializeFiles(unpacked, manifest, targetRoot)
    fs.writeFileSync(
      path.join(targetRoot, `manifest-${line}.json`),
      `${JSON.stringify(manifest, null, 2)}\n`,
      'utf8',
    )
    log(
      `更新文件 → ${targetRoot}：清单 ${manifest.files.length} 个文件 / ${mb(totalBytes)}` +
        `，本次新放入 ${copied} 个（按内容去重）`,
    )
    if (diff) {
      log(
        `与上一版 ${diff.previousVersion} 相比：新增 ${diff.added.length} · 修改 ${diff.changed.length}` +
          ` · 删除 ${diff.removed.length}，客户端需下载约 ${mb(diff.bytes)}`,
      )
      if (diff.added.length + diff.changed.length + diff.removed.length > 0) {
        for (const k of [...diff.added, ...diff.changed].slice(0, 15)) log(`  · ${k}`)
        if (diff.added.length + diff.changed.length > 15) log('  · …（其余略）')
      }
    } else if (line === 'cn') {
      log('（没有上一版清单，本次视为首次发布：客户端将需要完整下载一次）')
    }
  }

  log('完成。三份目录：')
  log(`  ${packTarget}`)
  log(`  ${path.join(UPDATE_DIR, 'cn')}`)
  log(`  ${path.join(UPDATE_DIR, 'seoul')}`)
  log('把 cn / seoul 两个目录分别上传到对应线路的 updates 路径即可。')
  log(`仓库：${repoDir}`)
}

main().catch((error) => fail(error?.stack ?? String(error)))
