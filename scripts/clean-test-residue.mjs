




































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




const PROJECT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

const args = new Set(process.argv.slice(2))
const dryRun = args.has('--dry-run')
const assumeYes = args.has('--yes')
const force = args.has('--force')

const MB = (bytes) => `${(bytes / 1024 / 1024).toFixed(1)} MB`








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
          
        }
      }
    }
  }
  walk(target)
  return total
}


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









const UPDATER_NAMES = [
  'soulmate-desktop-updater',
  'agent-desktop-updater',
  'jianyin_agent-updater',
]


const TEMP_DIR_PATTERNS = [
  /^agent-app-/,
  /^agent-app-warm-/,
  /^agent-exe-/,
  /^agent-acct-/,
  /^soulmate_selfcheck$/,
]

function collectTargets() {
  const targets = []

  
  for (const name of DATA_DIR_NAMES) {
    const dir = path.join(APPDATA, name)
    if (fs.existsSync(dir)) targets.push(dir)
  }
  for (const backup of listByPrefix(APPDATA, (name) =>
    DATA_DIR_NAMES.some((base) => name.startsWith(`${base}.backup-`)),
  )) {
    targets.push(backup)
  }

  
  for (const name of UPDATER_NAMES) {
    const dir = path.join(LOCALAPPDATA, name)
    if (fs.existsSync(dir)) targets.push(dir)
  }

  
  const oldInstall = path.join(LOCALAPPDATA, 'Programs', 'jianyin_agent')
  if (fs.existsSync(oldInstall)) targets.push(oldInstall)

  
  for (const pattern of TEMP_DIR_PATTERNS) {
    for (const dir of listByGlob(TEMP, pattern)) targets.push(dir)
  }

  
  for (const root of [
    path.join(PROJECT_DIR, 'desktop', 'release'),
    path.join(PROJECT_DIR, 'core', 'dist'),
  ]) {
    for (const dir of listByGlob(root, /^\.stale-/)) targets.push(dir)
  }

  
  
  
  
  return [...new Set(targets)]
}


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
