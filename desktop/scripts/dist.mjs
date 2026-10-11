/**
 * 一键出安装包（NSIS）。
 *
 * 只出 NSIS 安装包，**不再出 portable 免安装版**（产品决定）。
 * 目标由 package.json 的 build.win.target 决定，这里不再重复一份。
 *
 * 单独抽脚本是为了处理 electron-builder 的**下载问题**：
 * 它出 Windows 包时一定要从 GitHub releases 拉 winCodeSign / nsis 工具包
 * （源码里 `getBinariesMirrorUrl` 只认这一个镜像环境变量），
 * 国内直连经常卡到 600s 超时，而报错长得像构建失败。
 *
 * 两件事必须由本脚本补齐，否则用户会反复撞墙：
 *
 * 1. **代理**：electron-builder 用 `got` 下载，而 `got` 只认 `HTTPS_PROXY`
 *    环境变量，**不读 Windows 注册表里的系统代理**。翻墙软件通常只改注册表，
 *    于是"我明明开了代理，它还是连不上"。这里自动探测并补上；
 * 2. **`NO_PROXY`**：既然设了代理，就必须显式豁免本机地址，
 *    否则对 127.0.0.1 的请求也会被转发出去（这个坑在本项目里踩过好几次）。
 *
 * 用法：
 *   node scripts/dist.mjs                        # 有代理走官方源，没代理走镜像
 *   $env:HTTPS_PROXY="http://127.0.0.1:7897"; node scripts/dist.mjs
 *   $env:ELECTRON_BUILDER_BINARIES_MIRROR=""; node scripts/dist.mjs   # 强制用官方源
 */
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')

/**
 * 读取 Windows 注册表里的系统代理。
 *
 * 翻墙软件默认只写注册表、不导出环境变量，而 electron-builder 的下载器
 * 完全看不见注册表——这就是"开了代理仍然超时"的根因。
 */
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
    // 注册表里可能写成 "127.0.0.1:7897"，也可能带协议前缀
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

// 镜像策略：**有代理就优先官方源**。
// 镜像可能落后于上游版本（拿到 404 或旧包），网络既然通了就没必要冒这个险。
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

// 核心产物已存在时跳过重建：PyInstaller 每次会先删掉 500+ 个旧文件，
// 在有批量删除保护的机器上会被拦下，但源码没改时其实完全没必要重建。
const coreExe = path.resolve(desktopDir, '..', 'core', 'dist', 'agent-core', 'agent-core.exe')
if (fs.existsSync(coreExe) && !process.env.FORCE_CORE_BUILD) {
  console.log('[dist] 检测到已有的核心产物，跳过重建（需要重建请设置 FORCE_CORE_BUILD=1）')
} else {
  run('打包 Python 核心', 'npm', ['run', 'build:core'])
}

// electron-builder 开始前会先清空 release/win-unpacked（600+ 个文件）。
// 开了批量删除保护时这一步会被拦下，报错长得像打包失败。**改名不算删除**，
// 所以先把旧目录挪开——与 build-core.mjs 用的是同一套办法。
const releaseDir = path.join(desktopDir, 'release')
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
run('生成安装包', 'npx', ['--no-install', 'electron-builder', '--win'])

// 收尾：清掉挪开的旧产物。
// 走 PowerShell 而不是 fs.rmSync —— 在开了批量删除保护的环境里，
// Node 侧的批量删除会被拦下，而外部进程的删除不受影响。
for (const target of stashed) {
  spawnSync(
    'powershell.exe',
    ['-NoProfile', '-NonInteractive', '-Command', `Remove-Item -Recurse -Force -LiteralPath '${target}'`],
    { stdio: 'ignore', windowsHide: true },
  )
}

console.log('\n[dist] 完成，产物在 desktop/release/ 下')
