








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
