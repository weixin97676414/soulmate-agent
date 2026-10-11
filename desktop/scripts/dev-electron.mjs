/**
 * 开发模式启动器。
 *
 * 1. 等 Vite 开发服务器就绪（避免 Electron 先加载到空白页）；
 * 2. 编译主进程 TypeScript；
 * 3. 启动 Electron，并通过 VITE_DEV_SERVER_URL 指向 Vite。
 *
 * 主进程代码改动后需要重启本脚本（不做主进程热重载，行为更可预测）；
 * 渲染层代码由 Vite HMR 自动更新。
 */
import { spawn, spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import net from 'node:net'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const desktopDir = path.resolve(scriptDir, '..')
const VITE_PORT = 5173

function waitForPort(port, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const socket = net.connect({ port, host: '127.0.0.1' })
      socket.once('connect', () => {
        socket.destroy()
        resolve()
      })
      socket.once('error', () => {
        socket.destroy()
        if (Date.now() > deadline) {
          reject(new Error(`等待 Vite 开发服务器（端口 ${port}）超时`))
          return
        }
        setTimeout(attempt, 250)
      })
    }
    attempt()
  })
}

async function main() {
  process.stdout.write(`[dev] 等待 Vite 开发服务器（:${VITE_PORT}）…\n`)
  await waitForPort(VITE_PORT)
  process.stdout.write('[dev] Vite 已就绪，编译主进程…\n')

  const tsc = spawnSync(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['tsc', '-p', 'tsconfig.electron.json'],
    { cwd: desktopDir, stdio: 'inherit', shell: process.platform === 'win32' },
  )
  if (tsc.status !== 0) {
    process.exit(tsc.status ?? 1)
  }

  const electronPath = require('electron')
  process.stdout.write('[dev] 启动 Electron…\n')

  const child = spawn(electronPath, ['.'], {
    cwd: desktopDir,
    stdio: 'inherit',
    env: { ...process.env, VITE_DEV_SERVER_URL: `http://localhost:${VITE_PORT}` },
  })

  child.on('exit', (code) => process.exit(code ?? 0))
  for (const signal of ['SIGINT', 'SIGTERM']) {
    process.on(signal, () => child.kill())
  }
}

main().catch((error) => {
  process.stderr.write(`[dev] ${error.message}\n`)
  process.exit(1)
})
