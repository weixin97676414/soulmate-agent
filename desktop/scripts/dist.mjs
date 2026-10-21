























import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')







function detectSystemProxy() {
  if (process.platform !== 'win32') return null
  const key = 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings'
  try {
    const enabled = spawnSync('reg', ['query', key, '/v', 'ProxyEnable'], { encoding: 'utf-8' })
    if (!/0x1\b/.test(enabled.stdout ?? '')) return null

    const server = spawnSync('reg', ['query', key, '/v', 'ProxyServer'], { encoding: 'utf-8' })
    const matched = /ProxyServer\s+REG_SZ\s+(\S+)/.exec(server.stdout ?? '')
    const value = matched?.[1]?.trim()
    if (!value) return null
    
    return value.includes('://') ? value : `http://${value}`
  } catch {
    return null
  }
}

const proxy =
  process.env.HTTPS_PROXY ||
  process.env.https_proxy ||
  process.env.HTTP_PROXY ||
  process.env.http_proxy ||
  detectSystemProxy()

const env = { ...process.env }

if (proxy) {
  env.HTTPS_PROXY = proxy
  env.HTTP_PROXY = proxy
  env.NO_PROXY = [process.env.NO_PROXY, 'localhost,127.0.0.1,::1'].filter(Boolean).join(',')
  env.no_proxy = env.NO_PROXY
  console.log(`[dist] 检测到代理 ${proxy}（已为本机地址设置 NO_PROXY）`)
}



const explicit = process.env.ELECTRON_BUILDER_BINARIES_MIRROR
if (explicit) {
  env.ELECTRON_BUILDER_BINARIES_MIRROR = explicit
  console.log(`[dist] 使用指定的工具包镜像：${explicit}`)
} else if (!proxy) {
  env.ELECTRON_BUILDER_BINARIES_MIRROR = 'https://npmmirror.com/mirrors/electron-builder-binaries/'
  console.log('[dist] 无代理，改用 npmmirror 镜像（可用 ELECTRON_BUILDER_BINARIES_MIRROR 覆盖）')
} else {
  console.log('[dist] 使用官方源下载构建工具包')
}

const explicitElectron = process.env.ELECTRON_MIRROR
if (explicitElectron) {
  env.ELECTRON_MIRROR = explicitElectron
} else if (!proxy) {
  env.ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
}

const run = (label, command, args) => {
  console.log(`\n[dist] ${label}`)
  const result = spawnSync(command, args, {
    cwd: desktopDir,
    stdio: 'inherit',
    shell: process.platform === 'win32',
    env,
  })
  if (result.status !== 0) {
    console.error(`\n[dist] 步骤失败：${label}（退出码 ${result.status}）`)
    process.exit(result.status ?? 1)
  }
}









function newestMtimeMs(target, skipDirNames) {
  if (!fs.existsSync(target)) return 0
  const stat = fs.statSync(target)
  if (!stat.isDirectory()) return stat.mtimeMs

  let newest = 0
  const walk = (current) => {
    let entries
    try {
      entries = fs.readdirSync(current, { withFileTypes: true })
    } catch {
      return 
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) {
        if (skipDirNames.has(entry.name) || entry.name.endsWith('.egg-info')) continue
        walk(full)
      } else if (entry.isFile()) {
        try {
          const { mtimeMs } = fs.statSync(full)
          if (mtimeMs > newest) newest = mtimeMs
        } catch {
          
        }
      }
    }
  }
  walk(target)
  return newest
}










const coreDir = path.resolve(desktopDir, '..', 'core')
const coreExe = path.join(coreDir, 'dist', 'agent-core', 'agent-core.exe')
const CORE_SOURCES = [
  path.join(coreDir, 'src'),
  path.join(coreDir, 'pyproject.toml'),
  
  path.join(coreDir, 'build', 'agent-core.spec'),
]
const CORE_SKIP_DIRS = new Set([
  'dist',
  'build',
  '__pycache__',
  '.pytest_cache',
  '.ruff_cache',
  '.mypy_cache',
  '.venv',
  'node_modules',
])

const newestSourceMs = Math.max(...CORE_SOURCES.map((p) => newestMtimeMs(p, CORE_SKIP_DIRS)))
const coreExeMs = fs.existsSync(coreExe) ? fs.statSync(coreExe).mtimeMs : 0
const coreUpToDate = coreExeMs > 0 && newestSourceMs <= coreExeMs

const stamp = (ms) => (ms > 0 ? new Date(ms).toLocaleString() : '（无）')
if (process.env.FORCE_CORE_BUILD || !coreUpToDate) {
  console.log(
    process.env.FORCE_CORE_BUILD
      ? '[dist] FORCE_CORE_BUILD=1，强制重建核心'
      : `[dist] 核心源码比产物新（源码 ${stamp(newestSourceMs)} > 产物 ${stamp(coreExeMs)}），重建核心`,
  )
  run('打包 Python 核心', 'npm', ['run', 'build:core'])
} else {
  console.log(
    `[dist] 核心产物不比源码旧，跳过重建（产物 ${stamp(coreExeMs)}）。` +
      ' 需要强制重建请设置 FORCE_CORE_BUILD=1',
  )
}









const releaseDir = process.env.DIST_OUTPUT
  ? path.resolve(process.env.DIST_OUTPUT)
  : path.join(desktopDir, 'release')
const stashed = []
if (fs.existsSync(releaseDir)) {
  for (const name of fs.readdirSync(releaseDir)) {
    if (name === 'win-unpacked') {
      const from = path.join(releaseDir, name)
      const to = path.join(releaseDir, `.stale-${name}-${Date.now()}`)
      try {
        fs.renameSync(from, to)
        stashed.push(to)
        console.log(`[dist] 旧产物已挪到 ${path.basename(to)}（避免触发批量删除保护）`)
      } catch (error) {
        console.error(`[dist] 无法挪走旧产物 ${from}：${error}`)
        process.exit(1)
      }
    }
  }
}

run('构建前端与主进程', 'npm', ['run', 'build'])
run('生成安装包', 'npx', [
  '--no-install',
  'electron-builder',
  '--win',
  
  
  
  
  `--config.directories.output=${path.relative(desktopDir, releaseDir) || '.'}`,
])




for (const target of stashed) {
  spawnSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-Command', `Remove-Item -Recurse -Force -LiteralPath '${target}'`],
    { stdio: 'ignore', windowsHide: true },
  )
}













const packedCoreExe = path.join(
  releaseDir,
  'win-unpacked',
  'resources',
  'agent-core',
  'agent-core.exe',
)
let coreCheckFailed = ''
if (!fs.existsSync(packedCoreExe)) {
  coreCheckFailed = `包里没找到核心：${packedCoreExe}`
} else {
  const built = fs.statSync(coreExe)
  const packed = fs.statSync(packedCoreExe)
  if (built.size !== packed.size) {
    coreCheckFailed =
      '包里装的核心不是本次构建的产物：\n' +
      `    本次构建  ${path.relative(desktopDir, coreExe)}\n` +
      `      ${built.size} 字节 · ${new Date(built.mtimeMs).toLocaleString()}\n` +
      `    包里那份  ${path.relative(desktopDir, packedCoreExe)}\n` +
      `      ${packed.size} 字节 · ${new Date(packed.mtimeMs).toLocaleString()}`
  } else {
    console.log(
      `[dist] 核心核验通过：包内 agent-core.exe 与本次构建一致（${(packed.size / 1024 / 1024).toFixed(1)} MB）`,
    )
  }
}







try {
  const pkg = JSON.parse(fs.readFileSync(path.join(desktopDir, 'package.json'), 'utf8'))
  const expected = `${pkg.productName ?? 'Soulmate Agent'} Setup ${pkg.version}.exe`
  const installers = fs
    .readdirSync(releaseDir)
    .filter((name) => name.toLowerCase().endsWith('.exe'))
    .map((name) => ({
      name,
      size: fs.statSync(path.join(releaseDir, name)).size,
      mtimeMs: fs.statSync(path.join(releaseDir, name)).mtimeMs,
    }))
    .sort((a, b) => b.mtimeMs - a.mtimeMs)
  if (installers.length > 0) {
    const best = installers.find((item) => item.name === expected) ?? installers[0]
    console.log(
      `[dist] 安装包：${path.relative(desktopDir, path.join(releaseDir, best.name))}（${(best.size / 1024 / 1024).toFixed(1)} MB）`,
    )
  }
} catch {
  
}

console.log(`\n[dist] 完成，产物在 ${path.relative(desktopDir, releaseDir) || '.'} 下`)
console.log('[dist] 建议接着跑：npm run verify:core && npm run verify:app')

if (coreCheckFailed) {
  console.error(`\n[dist] ✗ 出包后核验失败：${coreCheckFailed}`)
  console.error('[dist]   包已生成，但核心对不上，**不要拿去测**。请清理 win-unpacked 后重出。')
  process.exit(1)
}
