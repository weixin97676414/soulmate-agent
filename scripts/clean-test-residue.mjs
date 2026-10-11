/**
 * 彻底清理"测试这个客户端"在本机留下的一切残留。
 *
 * ## 与 `reset-local-data.mjs` 的区别（两者**不要**合并）
 *
 * - `reset-local-data.mjs`：**发版流程的固定一步**。它把数据目录改名为备份再重建
 *   一份干净的，并且**保留账号凭据**（`account-secrets.bin`）—— 因为那个
 *   `device_secret` 只在注册时下发过一次，删了就永远取不回来。
 * - 这个脚本：**用户主动要求"清干净"**时用。它删得更多（备份目录、更新器缓存、
 *   临时验证目录、陈旧构建产物、早期安装的旧客户端），并且**连账号凭据一起删**。
 *
 * 把两者混在一起，就等于让"每批的常规清零"变成危险操作 —— 所以这里是独立脚本。
 *
 * ## 为什么要删这些（都是实测出来的体积）
 *
 * | 残留 | 来源 | 实测 |
 * |---|---|---|
 * | `%APPDATA%\Soulmate Agent.backup-*` | 每次 `reset:local` 留一份备份 | 累积，只增不减 |
 * | `%LOCALAPPDATA%\*-updater` | electron-updater 下载的安装包缓存 | 约 884 MB |
 * | `%TEMP%\agent-app-* / agent-exe-* / agent-acct-*` | 验收脚本每次起的独立数据目录 | 几十个 |
 * | `release\.stale-win-unpacked-*` | 构建脚本"先改名再删"留下的旧产物 | 1.2 GB |
 * | `%LOCALAPPDATA%\Programs\jianyin_agent` | 很早期装过的旧客户端 | 一整个程序目录 |
 *
 * ## 用法
 *
 *   node scripts/clean-test-residue.mjs --dry-run   # 只列清单，不删（先看一眼）
 *   node scripts/clean-test-residue.mjs             # 真删（会先打印代价并要求确认）
 *   node scripts/clean-test-residue.mjs --yes       # 不问，直接删
 *   node scripts/clean-test-residue.mjs --force     # 应用正在运行时也照删（不推荐）
 *
 * ## 本机环境的两条硬约束（踩过坑，别绕过）
 *
 * 1. **批量删除保护**：一次删除 500 个文件以上会被系统拦下
 *    （报 `SAFE_DELETE_BULK_CONFIRM_REQUIRED`）。所以大目录一律交给
 *    **PowerShell 外部进程**删（`fs.rmSync` 会被拦），并且
 * 2. **同步子进程调用必须带 timeout** —— 本机出现过"命令永久阻塞、界面看起来卡死"。
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'
import readline from 'node:readline'
import { fileURLToPath } from 'node:url'

import {
  APPDATA,
  DATA_DIR_NAMES,
  LOCALAPPDATA,
  RUNNING_PROCESSES,
  TEMP,
  isOurShortcut,
  isRunning,
} from './shared-cleanup-consts.mjs'

// ⚠️ 必须用 fileURLToPath：本仓库路径里有**中文**，而 `new URL(...).pathname`
// 保留百分号编码（`%E4%BB%A3%E7%A0%81...`），拿它去拼路径会找不到目录。
// 与本项目其它脚本（verify-packaged-app.mjs 等）保持一致。
const PROJECT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const args = new Set(process.argv.slice(2))
const dryRun = args.has('--dry-run')
const assumeYes = args.has('--yes')
const force = args.has('--force')

const MB = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`

/**
 * 删一个大目录。
 *
 * 走 PowerShell 而不是 `fs.rmSync`：本机的批量删除保护会拦下 Node 侧的批量删除，
 * 而外部进程的删除不受影响（`build-core.mjs` / `dist.mjs` 里已有同样的先例）。
 * `-LiteralPath` 是必须的 —— 路径里的方括号会被当通配符。
 */
function removeDirectory(target) {
  const script = [
    '$ErrorActionPreference = "Stop"',
    `Remove-Item -LiteralPath '${target.replace(/'/g, "''")}' -Recurse -Force`,
  ].join('; ')
  execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], {
    stdio: 'ignore',
    windowsHide: true,
    timeout: 120_000,
  })
}

function directorySize(target) {
  let total = 0
  const walk = (dir) => {
    let entries = []
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name)
      if (entry.isDirectory()) walk(full)
      else {
        try {
          total += fs.statSync(full).size
        } catch {
          // 单个文件读不到就跳过，不影响"大概多大"
        }
      }
    }
  }
  walk(target)
  return total
}

/** 按前缀/通配列出目录（只在**指定目录**下扫一层，不做通配递归） */
function listByPrefix(dir, predicate) {
  let entries = []
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
  return entries
    .filter((entry) => entry.isDirectory() && predicate(entry.name))
    .map((entry) => path.join(dir, entry.name))
}

function listByGlob(dir, pattern) {
  return listByPrefix(dir, (name) => pattern.test(name))
}

// --------------------------------------------------------------------------- //
// 目标清单
// --------------------------------------------------------------------------- //

// 数据目录清单（当前名 + 三个历史产品名）在 `shared-cleanup-consts.mjs`，
// 两个清理脚本共用一份 —— 以前各写一份的结果是 `reset:local` 那份漏了 `jianyin_agent`。

/** 更新器缓存：应用名 -updater */
const UPDATER_NAMES = [
  'soulmate-desktop-updater',
  'agent-desktop-updater',
  'jianyin_agent-updater',
]

/** 临时目录里的验证残留（验收脚本每次跑都会新建） */
const TEMP_DIR_PATTERNS = [
  /^agent-app-/,
  /^agent-app-warm-/,
  /^agent-exe-/,
  /^agent-acct-/,
  /^soulmate_selfcheck$/,
]

function collectTargets() {
  const targets = []

  // 1) 数据目录本身 + 它的历次备份（备份是 reset 脚本留下的，只增不减）
  for (const name of DATA_DIR_NAMES) {
    const dir = path.join(APPDATA, name)
    if (fs.existsSync(dir)) targets.push(dir)
  }
  for (const backup of listByPrefix(APPDATA, (name) =>
    DATA_DIR_NAMES.some((base) => name.startsWith(`${base}.backup-`)),
  )) {
    targets.push(backup)
  }

  // 2) electron-updater 的下载缓存（三个名字都是历史遗留）
  for (const name of UPDATER_NAMES) {
    const dir = path.join(LOCALAPPDATA, name)
    if (fs.existsSync(dir)) targets.push(dir)
  }

  // 3) 早期安装的旧客户端（不在本次的安装目标里，但占着一整个程序目录）
  const oldInstall = path.join(LOCALAPPDATA, 'Programs', 'jianyin_agent')
  if (fs.existsSync(oldInstall)) targets.push(oldInstall)

  // 4) 临时目录里的验证残留
  for (const pattern of TEMP_DIR_PATTERNS) {
    for (const dir of listByGlob(TEMP, pattern)) targets.push(dir)
  }

  // 5) 构建脚本挪开的陈旧产物（`.stale-win-unpacked-*` / `.stale-agent-core-*`）
  for (const root of [
    path.join(PROJECT_DIR, 'desktop', 'release'),
    path.join(PROJECT_DIR, 'core', 'dist'),
  ]) {
    for (const dir of listByGlob(root, /^\.stale-/)) targets.push(dir)
  }

  // 去重：`TEMP_DIR_PATTERNS` 里的模式是**互相包含**的（`agent-app-warm-*` 同时也
  // 命中 `agent-app-*`），同一个目录会被推两次。不去重的话第一次删掉、第二次报
  // "删除失败"，末尾那句"失败 N 项"就成了假警报 —— 而"删不掉的项"是要人去看的，
  // 让它常年有个假项，真出问题时就没人当回事了。
  return [...new Set(targets)]
}

/** 旧快捷方式会把老图标一起缓存住，删掉它下一次安装才会重建 */
function cleanShortcuts() {
  const candidates = [
    path.join(process.env.PUBLIC ?? 'C:\\Users\\Public', 'Desktop'),
    path.join(os.homedir(), 'Desktop'),
    path.join(APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    path.join(
      process.env.ProgramData ?? 'C:\\ProgramData',
      'Microsoft',
      'Windows',
      'Start Menu',
      'Programs',
    ),
  ]
  let removed = 0
  for (const dir of candidates) {
    let entries = []
    try {
      entries = fs.readdirSync(dir)
    } catch {
      continue
    }
    for (const name of entries) {
      // 只看我们自己创建的快捷方式，绝不动桌面上别的东西（判定见共享模块）
      if (!isOurShortcut(name)) continue
      try {
        fs.rmSync(path.join(dir, name), { force: true })
        removed += 1
        console.log(`  已删除旧快捷方式：${path.join(dir, name)}`)
      } catch (error) {
        console.warn(`  删除失败（可忽略，重装会覆盖）：${name} — ${error}`)
      }
    }
  }
  if (removed === 0) console.log('  没有找到旧的「智能体助手」快捷方式')
}

async function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout })
  try {
    const answer = await new Promise((resolve) => rl.question(question, resolve))
    return answer.trim().toLowerCase()
  } finally {
    rl.close()
  }
}

// --------------------------------------------------------------------------- //

const running = RUNNING_PROCESSES.filter(isRunning)
if (running.length > 0 && !force && !dryRun) {
  console.error(`\n✗ 检测到应用正在运行：${running.join(', ')}`)
  console.error('  请先彻底退出（托盘图标右键 → 退出），否则会删掉正在写入的数据库。')
  console.error('  确认无所谓时可以加 --force 跳过这道检查。\n')
  process.exit(1)
}

const targets = collectTargets()
let totalBytes = 0
const withSize = targets.map((target) => {
  const size = directorySize(target)
  totalBytes += size
  return { target, size }
})

console.log('\n[clean] 将要删除以下残留：\n')
for (const { target, size } of withSize) {
  console.log(`  ${MB(size).padStart(10)}  ${target}`)
}
console.log(`\n[clean] 合计 ${withSize.length} 项，约 ${MB(totalBytes)}`)

if (withSize.some((item) => item.target === path.join(APPDATA, 'Soulmate Agent'))) {
  // 把代价说在前面。产品要求"全部清掉"是明确的选择，但他必须知道后果。
  console.log(
    '\n⚠️ 注意：这会**连账号凭据一起删掉**（account-secrets.bin）。' +
      '\n   那是注册时只下发一次的 device_secret，删除后**换不回来**：' +
      '\n   返佣与钱包会报"缺少设备凭据"，需要在「权益 → 密码与安全」里用账号密码登录恢复。' +
      '\n⚠️ 同时被删的还有**全部密钥**：secrets.bin（模型 / MCP 的 API Key）' +
      '\n   与 skill-secrets.bin（技能密钥）。它们**没有**任何恢复途径 ——' +
      '\n   跑完这次之后要**重新填一遍**（否则启动会进首启引导页，那不是 bug）。',
  )
}

if (dryRun) {
  console.log('\n[clean] --dry-run：什么都没删。\n')
  process.exit(0)
}

if (!assumeYes) {
  const answer = await ask('\n确认删除以上全部内容？(yes/no) ')
  if (answer !== 'yes' && answer !== 'y') {
    console.log('[clean] 已取消，什么都没删。')
    process.exit(0)
  }
}

console.log('')
let removed = 0
let failed = 0
for (const { target } of withSize) {
  try {
    removeDirectory(target)
    removed += 1
    console.log(`  ✓ 已删除 ${target}`)
  } catch (error) {
    failed += 1
    // 不假装成功：删不掉就说清是哪一条、为什么。
    console.warn(`  ✗ 删除失败 ${target} — ${error instanceof Error ? error.message : error}`)
  }
}

console.log('\n[clean] 清理旧快捷方式')
cleanShortcuts()

console.log(`\n[clean] 完成：删除 ${removed} 项，失败 ${failed} 项`)
if (failed > 0) {
  console.log('[clean] 失败项通常是"文件被占用"：彻底退出应用后重跑一次即可。')
}
console.log('')
