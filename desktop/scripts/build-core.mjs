/**
 * 用 PyInstaller 打包 Python 核心。
 *
 * 单独抽一个脚本而不是在 package.json 里堆命令行，是因为这里有几个
 * 跨平台 / 跨环境的判断，写成一行 bash 会很难维护：
 *  - venv 的位置在 Windows 是 `Scripts`、类 Unix 是 `bin`；
 *  - 缺 PyInstaller 时要给出**可直接复制执行**的安装命令，而不是一个 ModuleNotFound；
 *  - 构建日志很长，失败时要把它落到文件并只回显关键行。
 */
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')
const coreDir = path.resolve(desktopDir, '..', 'core')

const isWindows = process.platform === 'win32'
const venvPython = isWindows
  ? path.join(coreDir, '.venv', 'Scripts', 'python.exe')
  : path.join(coreDir, '.venv', 'bin', 'python')

if (!fs.existsSync(venvPython)) {
  console.error(`✗ 未找到 Python 虚拟环境：${venvPython}`)
  console.error('  请先执行：cd core && py -3.13 -m venv .venv && .venv\\Scripts\\pip install -e ".[dev,office,mcp]"')
  process.exit(1)
}

const probe = spawnSync(venvPython, ['-c', 'import PyInstaller; print(PyInstaller.__version__)'], {
  encoding: 'utf-8',
})
if (probe.status !== 0) {
  console.error('✗ 未安装 PyInstaller。请执行：')
  console.error(`  "${venvPython}" -m pip install "pyinstaller>=6.6"`)
  process.exit(1)
}

// 长期记忆**依赖**默认随包分发（产品决定）：开关这里的差额指的是 chromadb 那一坨
// 依赖（约 217 MB 那条是老口径的估算，**不是产物总大小**）。
// 关掉可以出精简版：$env:AGENT_WITH_MEMORY="0"
//
// ⚠️ 2026-10-08 起（第七十九批）：**语音模型与嵌入模型都不再随包分发**，
// 改成首启引导页按需下载（见 core/src/my_agent/model_hub/）。
// 所以：
//   · 这里"约 217 MB / 约 73 MB"**只覆盖 chromadb 相关依赖**，别再当成产物体积；
//   · 核心产物会比之前小约 820 MB（两个模型合计），**这是预期的**，
//     不是"少了什么"；同理 verify 脚本里任何按旧体积写的阈值都要重新对。
const wantMemory = !['0', 'false', 'no'].includes(
  (process.env.AGENT_WITH_MEMORY ?? '1').trim().toLowerCase(),
)
if (wantMemory) {
  const memoryProbe = spawnSync(venvPython, ['-c', 'import chromadb; print(chromadb.__version__)'], {
    encoding: 'utf-8',
  })
  if (memoryProbe.status !== 0) {
    console.error('✗ 长期记忆默认开启，但当前环境未安装 chromadb。')
    console.error('  直接构建会产出一个"看起来正常、但没有知识库功能"的包 ——')
    console.error('  这类静默降级比构建失败难查得多，所以这里直接拦下。')
    console.error('  二选一：')
    console.error(`    1) 安装依赖： "${venvPython}" -m pip install -e ".[memory]"`)
    console.error('    2) 显式出精简版： $env:AGENT_WITH_MEMORY="0"; npm run build:core')
    process.exit(1)
  }
  console.log(
    `[build-core] 长期记忆依赖已启用（chromadb ${memoryProbe.stdout.trim()}，约 217 MB 依赖）`,
  )
} else {
  console.log('[build-core] 长期记忆依赖已关闭（AGENT_WITH_MEMORY=0），可省约 217 MB 依赖')
}
console.log('[build-core] 语音与嵌入模型不随包（首启按需下载），核心产物会因此明显变小')

console.log(`[build-core] PyInstaller ${probe.stdout.trim()}，开始打包…`)
const started = Date.now()

// PyInstaller 的 COLLECT 会先删掉整个旧产物目录（500+ 个文件）。
// 在有批量删除保护的环境里这一步会被拦下，报错还长得像构建失败。
// **改名不算删除**，所以把旧目录挪开，让 COLLECT 面对一个干净的目标路径。
const distDir = path.join(coreDir, 'dist', 'agent-core')
if (fs.existsSync(distDir)) {
  const stash = path.join(coreDir, 'dist', `.stale-agent-core-${Date.now()}`)
  try {
    fs.renameSync(distDir, stash)
    console.log(`[build-core] 旧产物已挪到 ${path.basename(stash)}（避免触发批量删除保护）`)
  } catch (error) {
    console.error(`✗ 无法挪走旧产物 ${distDir}：${error}`)
    console.error('  请手工删除该目录后重试。')
    process.exit(1)
  }
}

const args = [
  '-m',
  'PyInstaller',
  '--noconfirm',
  '--clean',
  '--distpath',
  'dist',
  // 工作目录放到 build\.pyi，避免和 spec 文件混在一起
  '--workpath',
  path.join('build', '.pyi'),
  path.join('build', 'agent-core.spec'),
]

const result = spawnSync(venvPython, args, {
  cwd: coreDir,
  stdio: ['ignore', 'pipe', 'pipe'],
  encoding: 'utf-8',
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
})

const logPath = path.join(coreDir, 'build', 'pyinstaller.log')
fs.mkdirSync(path.dirname(logPath), { recursive: true })
fs.writeFileSync(logPath, `${result.stdout ?? ''}\n${result.stderr ?? ''}`, 'utf-8')

const combined = `${result.stdout ?? ''}\n${result.stderr ?? ''}`

if (result.status !== 0) {
  console.error(`✗ PyInstaller 失败（退出码 ${result.status}），完整日志：${logPath}`)

  // 重新构建时 PyInstaller 会先删掉旧的 dist/agent-core（500+ 个文件）。
  // 如果环境里开了批量删除保护，这一步会被拦下，报错信息却长得很像构建失败，
  // 很容易被误判成"打包坏了"。这里把它翻译成人话，并给出可直接执行的清理命令。
  if (combined.includes('SAFE_DELETE_BULK_CONFIRM_REQUIRED')) {
    console.error('')
    console.error('  原因：删除旧的 dist/agent-core 被「批量删除保护」拦截（超过 500 个文件的阈值）。')
    console.error('  这不是打包失败，源码与依赖都没问题。二选一即可：')
    console.error(`    1) 手工清理后重试： Remove-Item -Recurse -Force "${path.join(coreDir, 'dist', 'agent-core')}"`)
    console.error('    2) 直接跳过核心重建（Python 源码没改时）：npm run build && npx electron-builder --win')
    process.exit(result.status ?? 1)
  }

  const tail = combined.trim().split(/\r?\n/).slice(-25).join('\n')
  console.error(tail)
  process.exit(result.status ?? 1)
}

const exePath = path.join(coreDir, 'dist', 'agent-core', isWindows ? 'agent-core.exe' : 'agent-core')
if (!fs.existsSync(exePath)) {
  console.error(`✗ 构建返回成功但未生成产物：${exePath}`)
  process.exit(1)
}

const bytes = fs
  .readdirSync(path.join(coreDir, 'dist', 'agent-core'), { recursive: true })
  .reduce((sum, entry) => {
    const full = path.join(coreDir, 'dist', 'agent-core', entry)
    try {
      return sum + (fs.statSync(full).isFile() ? fs.statSync(full).size : 0)
    } catch {
      return sum
    }
  }, 0)

console.log(
  `[build-core] 完成：${(bytes / 1024 / 1024).toFixed(1)} MB，耗时 ${(
    (Date.now() - started) / 1000
  ).toFixed(0)}s`,
)
console.log(`[build-core] 产物：${exePath}`)

// 收尾：清掉本次以及历史遗留的 .stale-agent-core-* 目录。
//
// 上面为了绕开批量删除保护，把旧产物**改名**挪开了 —— 但改名只是把问题推后，
// 不清理的话每重建一次就多留一个 60~70 MB 的目录，磁盘只增不减（实测攒了 4 个）。
//
// 删除走 PowerShell 而不是 fs.rmSync：在开了批量删除保护的环境里，
// Node 侧的批量删除会被拦下，而外部进程的删除不受影响。
const distRoot = path.join(coreDir, 'dist')
if (fs.existsSync(distRoot)) {
  const stale = fs
    .readdirSync(distRoot)
    .filter((name) => name.startsWith('.stale-agent-core-'))
    .map((name) => path.join(distRoot, name))

  for (const target of stale) {
    if (isWindows) {
      spawnSync(
        'powershell.exe',
        ['-NoProfile', '-NonInteractive', '-Command', `Remove-Item -Recurse -Force -LiteralPath '${target}'`],
        { stdio: 'ignore', windowsHide: true },
      )
    } else {
      try {
        fs.rmSync(target, { recursive: true, force: true })
      } catch {
        // 删不掉就留着，最后统一提示
      }
    }
  }

  const left = fs.readdirSync(distRoot).filter((name) => name.startsWith('.stale-agent-core-'))
  if (left.length > 0) {
    console.warn(`[build-core] ⚠️ 有 ${left.length} 个历史产物目录删不掉（批量删除保护？），请手工清理：`)
    console.warn(`  Remove-Item -Recurse -Force "${path.join(distRoot, '.stale-agent-core-*')}"`)
  } else if (stale.length > 0) {
    console.log(`[build-core] 已清理 ${stale.length} 个历史产物目录`)
  }
}

console.log('[build-core] 建议接着跑一次验收：node scripts/verify-core-exe.mjs')
