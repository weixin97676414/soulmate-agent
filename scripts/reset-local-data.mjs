/**
 * 把本机数据目录清回"全新安装"的状态。
 *
 * ## 为什么需要它
 *
 * 反复测同一件事时，上一次留下的配置会一直影响下一次：模型配置、加密密钥、
 * 历史会话、日志、Chromium 的各种缓存。于是"改了没生效"和"改动真没生效"
 * 长得一模一样 —— 排查时最怕的就是这种。
 *
 * 所以每次重新测试之前先清零，让起点确定。
 *
 * ## 为什么是"改名"而不是"删除"
 *
 * 那个目录里有用户的真实 API Key 与历史会话。清零的目的是**从零测试**，
 * 而留一份备份的成本接近零、误删的代价却是不可逆的。
 * 真的不想要备份时用 `--purge`。
 *
 * ## 用法
 *
 *   node scripts/reset-local-data.mjs               # 备份后清空（推荐）
 *   node scripts/reset-local-data.mjs --purge       # 直接删除，不留备份
 *   node scripts/reset-local-data.mjs --shortcuts   # 顺带清掉旧快捷方式并刷新图标缓存
 *   node scripts/reset-local-data.mjs --force       # 应用正在运行时也照做（不推荐）
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

import { APPDATA, RUNNING_PROCESSES, dataDirs, isOurShortcut, isRunning } from './shared-cleanup-consts.mjs'

// 数据目录名 / 运行中进程名 / 快捷方式判定都从 `shared-cleanup-consts.mjs` 来 ——
// 以前两个清理脚本各写一份，而且**已经漂移**（这里少了一个更早的产品名
// `jianyin_agent`，"清零"遇到那套老数据时会只清一半）。见那个文件的说明。

const args = new Set(process.argv.slice(2))
const purge = args.has('--purge')
const withShortcuts = args.has('--shortcuts')
const force = args.has('--force')

/**
 * 清数据时**必须保留**的文件（相对数据目录）。
 *
 * 只有账号凭据这一份：里面是 `device_secret`，而它按接口文档**只在注册响应里出现过
 * 一次**、之后再也拿不回来（后端仍记得这台设备的账号，所以客户端也不会重新注册）。
 * 删了它的后果是所有**需要设备签名**的接口（返佣、钱包）永久报"缺少设备凭据"。
 *
 * ⚠️ 就是这么撞出来的：交付前在这里清零数据 → 用户装上后返佣取不到，
 * 而界面当时只说"缺少设备凭据"，谁也不知道为什么。清账号列表（account.json）
 * 仍然是清的，所以"全新安装"这件事没有被破坏 —— 首启照样走查号流程，
 * 只是这次它手里还有凭据。
 *
 * ⚠️ **这不等于"你的 Key 保住了"**：模型 / MCP 的 API Key（`secrets.bin`）与
 * 技能密钥（`skill-secrets.bin`）**不在**保留清单里，它们会随数据目录一起被清掉，
 * 下次要重新填一次。这个脚本**刻意不保留它们**（"从零测试"就该连 Key 一起走），
 * 但必须在输出里说清楚 —— 否则用户会以为是"改动没生效"。
 */
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
          // 单个文件读不到就跳过，不影响"大概多大"这个判断
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

/** 旧快捷方式会把老图标一起缓存住，删掉它下一次安装才会重建 */
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

  // 图标缓存是系统级的，安装包无法保证立刻刷新。ie4uinit 是刷新它的官方入口，
  // 失败也无所谓（下次重启资源管理器同样会刷新），所以不把它当错误。
  try {
    // ⚠️ 必须带 timeout：本机出现过"外部命令永久阻塞"，清零又是发版流程的固定一步
    execFileSync('ie4uinit.exe', ['-show'], { stdio: 'ignore', windowsHide: true, timeout: 20_000 })
    console.log('  已请求刷新 Windows 图标缓存')
  } catch {
    console.log('  图标缓存刷新未执行（不影响使用，必要时重启资源管理器）')
  }
}

// --------------------------------------------------------------------------- //

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
      // 显式要求"彻底删"就照做，但必须把代价说出来（见 KEEP_FILES 的说明）
      console.warn(
        `[reset] ⚠️ 账号凭据（${inDanger.join('、')}）也一起删了：下次启动返佣与钱包会报` +
          '"缺少设备凭据"，且**换不回来**，只能在「权益 → 密码与安全」里用账号密码登录恢复',
      )
    }
  } else {
    const backup = `${dataDir}.backup-${timestamp()}`
    // 同一分区内的改名是瞬时的，几百 MB 也不会等；比"复制一份再删"干净得多
    fs.renameSync(dataDir, backup)
    // 把"必须保留"的文件搬回新目录（见 KEEP_FILES 的说明）
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
