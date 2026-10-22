












































import { spawnSync } from 'node:child_process'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')
const repoDir = path.resolve(desktopDir, '..')







const RELEASE_ROOT =
  process.env.PUBLISH_ROOT ||
  (process.platform === 'darwin'
    ? path.join(process.env.HOME || '.', 'soulmate-publish')
    : 'D:\\win版客户端开发')
const PACK_DIR = path.join(RELEASE_ROOT, '打包文件')
const UPDATE_DIR = path.join(RELEASE_ROOT, '更新文件')





const LINES = {
  cn: {
    baseUrl: 'https://china.xinjianxue.com/updates',
    
    
    
    fullPackage: (version) =>
      `https://china.xinjianxue.com/download/win/Soulmate-Agent-Setup-${version}.exe`,
  },
  seoul: {
    baseUrl: 'https://raw.githubusercontent.com/weixin97676414/soulmate-agent/main/updates',
    fullPackage: (version) =>
      `https://github.com/weixin97676414/soulmate-agent/releases/download/v${version}/Soulmate-Agent-Setup-${version}.exe`,
  },
}


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






function sha256(file) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash('sha256')
    fs.createReadStream(file)
      .on('data', (chunk) => hash.update(chunk))
      .on('end', () => resolve(hash.digest('hex')))
      .on('error', reject)
  })
}


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
  
  
  run('构建并打包（scripts/dist.mjs）', 'node', ['scripts/dist.mjs'])
}

function resolveUnpacked() {
  const explicit = value('unpacked')
  const fallback = path.join(desktopDir, 'release', process.platform === 'darwin' ? 'mac' : 'win-unpacked')
  const dir = explicit ? path.resolve(explicit) : fallback
  if (!fs.existsSync(dir)) fail(`找不到打包产物目录：${dir}`)
  return dir
}





function selfCheck(unpacked) {
  log('自检：产物是否真的不含注释')
  const problems = []

  
  const maps = [
    ...walk(path.join(desktopDir, 'dist')),
    ...walk(path.join(desktopDir, 'dist-electron')),
    ...walk(path.join(unpacked, 'resources', 'dist')),
  ].filter((file) => file.endsWith('.map'))
  if (maps.length) problems.push(`产物里存在 sourcemap（${maps.length} 个）：${maps[0]}`)

  
  const mainJs = path.join(desktopDir, 'dist-electron', 'electron', 'main.js')
  if (fs.existsSync(mainJs)) {
    const source = fs.readFileSync(mainJs, 'utf8')
    if (/^\s*\/\//m.test(source) || /^\s*\/\*/m.test(source)) {
      problems.push('dist-electron/electron/main.js 里仍有行首注释（removeComments 被关掉了？）')
    }
  }

  
  const indexHtml = path.join(unpacked, 'resources', 'dist', 'index.html')
  if (!fs.existsSync(indexHtml)) {
    problems.push('打包产物里没有 resources/dist/index.html（dist 没被打进 extraResources？）')
  } else {
    const html = fs.readFileSync(indexHtml, 'utf8')
    if (!html.includes('Content-Security-Policy')) problems.push('index.html 里没有 CSP meta')
    const absolute = html.match(/(src|href)="\/(?!\/)/g)
    if (absolute) problems.push('index.html 里有以 / 开头的绝对资源路径（file:// 下会白屏）')
  }

  







  const assets = walk(path.join(unpacked, 'resources', 'dist', 'assets')).filter((f) => f.endsWith('.js'))
  for (const asset of assets) {
    const source = fs.readFileSync(asset, 'utf8')
    const avgLine = source.length / Math.max(1, source.split('\n').length)
    if (avgLine < 200) {
      problems.push(`前端资源看着没被压缩（${path.basename(asset)} 平均行长仅 ${Math.round(avgLine)} 字符）`)
      break
    }
  }

  








  for (const rel of ['scripts/verify-packaged-app.mjs', 'scripts/verify-core-exe.mjs']) {
    const file = path.join(repoDir, rel)
    if (!fs.existsSync(file)) {
      
      problems.push(`验收脚本不见了：${rel}（被改名/删除？）`)
      continue
    }
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' })
    if (result.status !== 0) {
      const detail = (result.error?.message || result.stderr || '')
        .trim()
        .split('\n')
        .filter(Boolean)
        .slice(-3)
        .join(' / ')
      problems.push(`${rel} 语法不通（验收根本跑不起来）：${detail}`)
    }
  }

  if (problems.length) {
    for (const item of problems) console.error(`[publish] ✗ ${item}`)
    fail('自检未通过，已中止（没有生成任何发布目录）')
  }
  log(`自检通过：无 sourcemap · 主进程无注释 · 页面用相对路径 · 前端已压缩 · 验收脚本语法可解析`)
}











function isInScope(relPosix) {
  return UPDATE_SCOPE.some(
    (scope) => relPosix === scope.dir || relPosix.startsWith(`${scope.dir}/`),
  )
}














async function outOfScopeFingerprint(unpacked) {
  const entries = []
  for (const full of walk(unpacked)) {
    const rel = toPosix(path.relative(unpacked, full))
    if (isInScope(rel)) continue
    entries.push([rel, fs.statSync(full).size])
  }
  entries.sort((a, b) => (a[0] < b[0] ? -1 : 1))
  const hashOf = async (rel) => {
    const full = path.join(unpacked, rel)
    return fs.existsSync(full) ? await sha256(full) : ''
  }
  return {
    exe_sha256: await hashOf('resources/agent-core/agent-core.exe'),
    asar_sha256: await hashOf('resources/app.asar'),
    entries,
  }
}







function decideMinFrom({ version, previous, previousPrint, currentPrint }) {
  if (!previous) return { minFrom: version, reason: '没有上一版清单（首次发布，客户端本来就得完整下载）' }
  if (!previousPrint) {
    return {
      minFrom: version,
      reason: '上一版没有「范围外指纹」（本机制上线前发布的），保守起见这一版仍强制整包',
    }
  }
  if (previousPrint.exe_sha256 !== currentPrint.exe_sha256) {
    return { minFrom: version, reason: 'agent-core.exe 变了（核心本体不在增量范围）' }
  }
  if (previousPrint.asar_sha256 !== currentPrint.asar_sha256) {
    return { minFrom: version, reason: 'app.asar 变了（Electron 主进程不在增量范围）' }
  }
  if (JSON.stringify(previousPrint.entries) !== JSON.stringify(currentPrint.entries)) {
    return { minFrom: version, reason: '核心依赖（_internal 里非 my_agent 的部分）变了' }
  }
  return {
    minFrom: previous.min_from || version,
    reason: `范围外没变 ⇒ 允许增量（min_from 保持 ${previous.min_from || version}）`,
  }
}

async function buildManifest(unpacked, version, line, minFrom) {
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
      






      min_from: minFrom,
      line,
      generated_at: new Date().toISOString(),
      base_url: LINES[line].baseUrl,
      
      
      full_package: LINES[line].fullPackage(version),
      files,
    },
    totalBytes,
  }
}










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

  const referenced = new Set(manifest.files.map((item) => item.sha256))
  let removed = 0
  for (const entry of fs.readdirSync(filesDir)) {
    const bucketDir = path.join(filesDir, entry)
    if (!fs.statSync(bucketDir).isDirectory()) continue
    for (const name of fs.readdirSync(bucketDir)) {
      if (!name.endsWith('.bin')) continue
      const sha = name.slice(0, -'.bin'.length)
      if (referenced.has(sha)) continue
      fs.rmSync(path.join(bucketDir, name))
      removed += 1
    }
    if (fs.readdirSync(bucketDir).length === 0) fs.rmdirSync(bucketDir)
  }
  return { copied, removed }
}


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





async function main() {
  const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'))
  const version = value('version') ?? pkg.version
  log(`版本 ${version}`)

  if (!flag('skip-build')) buildAndPack()
  else log('跳过构建与打包（--skip-build）')

  const unpacked = resolveUnpacked()
  log(`打包产物：${unpacked}`)

  selfCheck(unpacked)

  
  const packTarget = path.join(PACK_DIR, `无注释-${version}`)
  fs.mkdirSync(packTarget, { recursive: true })
  const setupName =
    process.platform === 'darwin'
      ? `Soulmate Agent-${version}.dmg`
      : `Soulmate Agent Setup ${version}.exe`
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

  
  
  
  
  const currentPrint = await outOfScopeFingerprint(unpacked)

  for (const line of Object.keys(LINES)) {
    const targetRoot = path.join(UPDATE_DIR, line)
    const previousManifestFile = path.join(targetRoot, `manifest-${line}.json`)
    const previous = fs.existsSync(previousManifestFile)
      ? JSON.parse(fs.readFileSync(previousManifestFile, 'utf8'))
      : null
    const printFile = path.join(targetRoot, `out-of-scope-${line}.json`)
    const previousPrint = fs.existsSync(printFile)
      ? JSON.parse(fs.readFileSync(printFile, 'utf8'))
      : null
    const { minFrom, reason } = decideMinFrom({ version, previous, previousPrint, currentPrint })
    log(`更新策略（${line}）：${reason}`)

    const { manifest, totalBytes } = await buildManifest(unpacked, version, line, minFrom)
    




    const diff = line === 'cn' ? diffAgainstPrevious(manifest) : null
    fs.mkdirSync(targetRoot, { recursive: true })
    const { copied, removed } = await materializeFiles(unpacked, manifest, targetRoot)
    fs.writeFileSync(
      path.join(targetRoot, `manifest-${line}.json`),
      `${JSON.stringify(manifest, null, 2)}\n`,
      'utf8',
    )
    
    
    fs.writeFileSync(
      printFile,
      `${JSON.stringify({ version, generated_at: new Date().toISOString(), ...currentPrint }, null, 2)}\n`,
      'utf8',
    )
    log(
      `更新文件 → ${targetRoot}：清单 ${manifest.files.length} 个文件 / ${mb(totalBytes)}` +
        `，本次新放入 ${copied} 个（按内容去重）` +
        (removed > 0 ? `，清理不再被引用的残留 ${removed} 个` : ''),
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



const isEntry =
  Boolean(process.argv[1]) && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
if (isEntry) main().catch((error) => fail(error?.stack ?? String(error)))

export { decideMinFrom, isInScope, outOfScopeFingerprint }
