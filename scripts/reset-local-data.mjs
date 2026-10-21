























import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

import { APPDATA, RUNNING_PROCESSES, dataDirs, isOurShortcut, isRunning } from './shared-cleanup-consts.mjs'





const args = new Set(process.argv.slice(2))
const purge = args.has('--purge')
const withShortcuts = args.has('--shortcuts')
const force = args.has('--force')


















const KEEP_FILES = ['account-secrets.bin']

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

function timestamp() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  return (
    `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}` +
    `-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`
  )
}


function clearShortcuts() {
  const candidates = [
    path.join(process.env.PUBLIC ?? 'C:\\Users\\Public', 'Desktop'),
    path.join(os.homedir(), 'Desktop'),
    path.join(APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    path.join(process.env.ProgramData ?? 'C:\\ProgramData', 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
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

  
  
  try {
    
    execFileSync('ie4uinit.exe', ['-show'], { stdio: 'ignore', windowsHide: true, timeout: 20_000 })
    console.log('  已请求刷新 Windows 图标缓存')
  } catch {
    console.log('  图标缓存刷新未执行（不影响使用，必要时重启资源管理器）')
  }
}



const running = RUNNING_PROCESSES.filter(isRunning)
if (running.length > 0 && !force) {
  console.error(`\n✗ 检测到应用正在运行：${running.join(', ')}`)
  console.error('  请先彻底退出（托盘图标右键 → 退出），否则会删掉正在写入的数据库。')
  console.error('  确认无所谓时可以加 --force 跳过这道检查。\n')
  process.exit(1)
}

for (const dataDir of dataDirs) {
  console.log(`\n[reset] 数据目录：${dataDir}`)

  if (!fs.existsSync(dataDir)) {
    console.log('[reset] 目录不存在，跳过')
    continue
  }

  const sizeMb = (directorySize(dataDir) / 1024 / 1024).toFixed(1)
  console.log(`[reset] 当前占用：${sizeMb} MB`)

  if (purge) {
    const inDanger = KEEP_FILES.filter((name) => fs.existsSync(path.join(dataDir, name)))
    fs.rmSync(dataDir, { recursive: true, force: true })
    console.log('[reset] 已直接删除（未留备份）')
    if (inDanger.length) {
      
      console.warn(
        `[reset] ⚠️ 账号凭据（${inDanger.join('、')}）也一起删了：下次启动返佣与钱包会报` +
          '"缺少设备凭据"，且**换不回来**，只能在「权益 → 密码与安全」里用账号密码登录恢复',
      )
    }
  } else {
    const backup = `${dataDir}.backup-${timestamp()}`
    
    fs.renameSync(dataDir, backup)
    
    fs.mkdirSync(dataDir, { recursive: true })
    for (const name of KEEP_FILES) {
      const from = path.join(backup, name)
      if (!fs.existsSync(from)) continue
      fs.renameSync(from, path.join(dataDir, name))
      console.log(`[reset] 已保留账号凭据：${name}（删了它，返佣/钱包就永久取不到数据）`)
    }
    console.log(`[reset] 已备份并清空 -> ${backup}`)
    console.log(
      '[reset] ⚠️ 模型 / MCP 的 API Key（secrets.bin）与技能密钥（skill-secrets.bin）' +
        '也一起清了（只有账号凭据被保留）—— 下次启动要**重新填一次 Key**，' +
        '否则界面会走首启引导页，那不是 bug。',
    )
    console.log('[reset] 确认新版没问题后可以手动删掉这份备份')
  }
}

if (withShortcuts) {
  console.log('\n[reset] 清理旧快捷方式')
  clearShortcuts()
}

console.log('\n[reset] 完成：下次启动应用会按全新安装的状态初始化\n')
