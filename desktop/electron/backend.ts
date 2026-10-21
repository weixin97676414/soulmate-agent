








import { spawn, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

















async function killProcessTree(proc: ChildProcess): Promise<void> {
  const pid = proc.pid
  if (pid === undefined) return

  if (process.platform === 'win32') {
    await new Promise<void>((resolve) => {
      
      const killer = spawn('taskkill', ['/PID', String(pid), '/T', '/F'], {
        windowsHide: true,
        stdio: 'ignore',
      })
      let done = false
      const finish = () => {
        if (done) return
        done = true
        resolve()
      }
      
      
      
      
      const timer = setTimeout(() => {
        try {
          killer.kill()
        } catch {
          
        }
        finish()
      }, 5_000)
      killer.on('close', () => {
        clearTimeout(timer)
        finish()
      })
      
      
      killer.on('error', () => {
        clearTimeout(timer)
        finish()
      })
    })
  }

  
  
  try {
    proc.kill('SIGKILL')
  } catch {
    
  }
}

import { app } from 'electron'

import type { BackendInfo, BackendState, BackendStatus } from '../shared/bridge'
import { logDesktop } from './desktop-log'
import type { SecretsStore } from './secrets'
import type { SkillSecretsStore } from './skill-secrets'

const HANDSHAKE_PREFIX = 'AGENT_CORE_READY'
const START_TIMEOUT_MS = 30_000
const MAX_RESTARTS = 3







const STABLE_RUN_MS = 30_000
const GRACEFUL_SHUTDOWN_MS = 3_000






const CORE_FETCH_TIMEOUT_MS = 20_000










export async function coreFetch(
  info: Pick<BackendInfo, 'baseUrl' | 'token'>,
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const { timeoutMs = CORE_FETCH_TIMEOUT_MS, headers, signal, ...rest } = init
  const controller = new AbortController()
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null
  
  const forward = () => controller.abort()
  signal?.addEventListener('abort', forward, { once: true })
  const merged = new Headers(headers)
  merged.set('X-Local-Token', info.token)
  try {
    return await fetch(`${info.baseUrl}${path}`, {
      ...rest,
      headers: merged,
      signal: controller.signal,
    })
  } finally {
    if (timer) clearTimeout(timer)
    signal?.removeEventListener('abort', forward)
  }
}

interface LaunchSpec {
  command: string
  args: string[]
  cwd: string
  mode: 'development' | 'packaged'
}

export class BackendManager {
  private proc: ChildProcess | null = null
  private info: BackendInfo | null = null
  private restarts = 0
  







  private readyAt = 0
  private stopping = false
  private starting: Promise<BackendInfo> | null = null
  private readonly logBuffer: string[] = []

  onStatus?: (status: BackendStatus) => void
  onLog?: (line: string, stream: 'stdout' | 'stderr') => void

  constructor(
    private readonly dataDir: string,
    
    private readonly secrets?: SecretsStore,
    






    private readonly skillSecrets?: SkillSecretsStore,
  ) {}

  get current(): BackendInfo | null {
    return this.info
  }

  





  get hasProcess(): boolean {
    return this.proc !== null
  }

  get logs(): string[] {
    return this.logBuffer.slice(-200)
  }

  
  
  
  private buildLaunchSpec(): LaunchSpec {
    if (app.isPackaged) {
      
      const dir = path.join(process.resourcesPath, 'agent-core')
      const exe = process.platform === 'win32' ? 'agent-core.exe' : 'agent-core'
      const command = path.join(dir, exe)
      if (!fs.existsSync(command)) {
        throw new Error(
          `未找到后端可执行文件：${command}\n请先执行 npm run build:core 生成后端产物。`,
        )
      }
      return {
        command,
        args: ['--port', '0', '--data-dir', this.dataDir],
        cwd: dir,
        mode: 'packaged',
      }
    }

    
    const coreDir = path.resolve(__dirname, '../../../core')
    const venvPython =
      process.platform === 'win32'
        ? path.join(coreDir, '.venv', 'Scripts', 'python.exe')
        : path.join(coreDir, '.venv', 'bin', 'python')

    const command = fs.existsSync(venvPython) ? venvPython : 'python'
    return {
      command,
      args: ['-m', 'my_agent', '--port', '0', '--data-dir', this.dataDir],
      cwd: coreDir,
      mode: 'development',
    }
  }

  
  
  
  async start(): Promise<BackendInfo> {
    if (this.info && this.proc && !this.proc.killed) return this.info
    if (this.starting) return this.starting

    this.starting = this.spawnOnce().finally(() => {
      this.starting = null
    })
    return this.starting
  }

  private spawnOnce(): Promise<BackendInfo> {
    return new Promise<BackendInfo>((resolve, reject) => {
      let spec: LaunchSpec
      try {
        spec = this.buildLaunchSpec()
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        this.emitStatus('failed', message)
        reject(new Error(message))
        return
      }

      this.emitStatus('starting', '正在启动智能体核心…')
      this.pushLog(`[desktop] spawn ${spec.command} ${spec.args.join(' ')}`, 'stdout')

      
      
      let secretsFile: string | undefined
      try {
        secretsFile = this.secrets?.materialize()
      } catch (error) {
        console.error('[desktop] 密钥交接文件写入失败，本次将以空密钥启动:', error)
      }

      
      
      
      let skillSecretsFile: string | undefined
      try {
        skillSecretsFile = this.skillSecrets?.materialize()
      } catch (error) {
        console.error('[desktop] 技能密钥交接文件写入失败，本次将以空密钥启动:', error)
      }

      const proc = spawn(spec.command, spec.args, {
        cwd: spec.cwd,
        windowsHide: true,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: {
          ...process.env,
          
          PYTHONUTF8: '1',
          PYTHONIOENCODING: 'utf-8',
          PYTHONUNBUFFERED: '1',
          AGENT_DATA_DIR: this.dataDir,
          ...(secretsFile ? { AGENT_SECRETS_FILE: secretsFile } : {}),
          ...(skillSecretsFile ? { AGENT_SKILL_SECRETS_FILE: skillSecretsFile } : {}),
        },
      })
      this.proc = proc

      let settled = false
      let stdoutBuffer = ''
      const timer = setTimeout(() => {
        if (settled) return
        settled = true
        this.pushLog('[desktop] 启动超时，未收到握手信息', 'stderr')
        
        
        
        logDesktop(`[backend] 启动超时：${START_TIMEOUT_MS}ms 内未收到握手信息，终止进程`)
        this.emitStatus('failed', '智能体核心启动超时，请查看日志。')
        proc.kill()
        reject(new Error('后端启动超时'))
      }, START_TIMEOUT_MS)

      proc.stdout?.setEncoding('utf-8')
      proc.stdout?.on('data', (chunk: string) => {
        this.pushLog(chunk, 'stdout')
        stdoutBuffer += chunk

        
        let index: number
        while ((index = stdoutBuffer.indexOf('\n')) >= 0) {
          const line = stdoutBuffer.slice(0, index).trim()
          stdoutBuffer = stdoutBuffer.slice(index + 1)
          if (!line.startsWith(HANDSHAKE_PREFIX)) continue

          const payload = line.slice(HANDSHAKE_PREFIX.length).trim()
          try {
            const parsed = JSON.parse(payload) as { port: number; token: string; pid: number }
            this.info = {
              port: parsed.port,
              token: parsed.token,
              pid: parsed.pid,
              baseUrl: `http://127.0.0.1:${parsed.port}`,
              mode: spec.mode,
            }
            if (!settled) {
              settled = true
              clearTimeout(timer)
              
              
              this.readyAt = Date.now()
              this.emitStatus('ready', '智能体核心已就绪')
              
              
              
              logDesktop(`[backend] 核心已就绪 baseUrl=${this.info?.baseUrl ?? '?'}`)
              
              this.secrets?.cleanupTempFile()
              resolve(this.info)
            }
          } catch (error) {
            this.pushLog(`[desktop] 握手信息解析失败: ${String(error)}`, 'stderr')
          }
        }
      })

      proc.stderr?.setEncoding('utf-8')
      proc.stderr?.on('data', (chunk: string) => this.pushLog(chunk, 'stderr'))

      proc.on('error', (error) => {
        const message = `无法启动后端进程：${error.message}`
        this.pushLog(`[desktop] ${message}`, 'stderr')
        clearTimeout(timer)
        
        this.secrets?.cleanupTempFile()
        if (!settled) {
          settled = true
          this.emitStatus('failed', message)
          reject(new Error(message))
        }
      })

      proc.on('exit', (code, signal) => {
        clearTimeout(timer)
        this.pushLog(`[desktop] 后端进程退出 code=${code} signal=${signal}`, 'stdout')
        
        
        
        logDesktop(
          `[backend] 核心进程退出 code=${code} signal=${signal} ` +
            `stopping=${this.stopping} settled=${settled} restarts=${this.restarts}`,
        )
        this.proc = null
        this.info = null

        if (this.stopping) {
          this.emitStatus('stopped', '智能体核心已停止')
          return
        }

        if (!settled) {
          settled = true
          const message = `智能体核心启动失败（退出码 ${code}），请查看日志。`
          this.emitStatus('failed', message)
          reject(new Error(message))
          return
        }

        void this.scheduleRestart()
      })
    })
  }

  private async scheduleRestart(): Promise<void> {
    
    
    if (this.readyAt && Date.now() - this.readyAt >= STABLE_RUN_MS) {
      this.restarts = 0
    }
    this.readyAt = 0
    if (this.restarts >= MAX_RESTARTS) {
      this.emitStatus('failed', `智能体核心反复异常退出，已停止自动重启（${MAX_RESTARTS} 次）。`)
      
      
      logDesktop(`[backend] 核心连续异常退出 ${this.restarts} 次，停止自动重启`)
      return
    }
    this.restarts += 1
    this.emitStatus('restarting', `智能体核心意外退出，正在重启（第 ${this.restarts} 次）…`)
    logDesktop(`[backend] 核心意外退出，第 ${this.restarts} 次自动重启（本进程内）`)
    await new Promise((resolve) => setTimeout(resolve, 1000 * this.restarts))
    if (this.stopping) return
    try {
      await this.start()
    } catch {
      
    }
  }

  async restart(): Promise<BackendInfo> {
    await this.stop()
    this.stopping = false
    
    
    this.restarts = 0
    this.readyAt = 0
    return this.start()
  }

  
  
  
  async stop(): Promise<void> {
    this.stopping = true
    const proc = this.proc
    const info = this.info
    if (!proc) return

    
    if (info) {
      try {
        
        await coreFetch(info, '/v1/shutdown', { method: 'POST', timeoutMs: 1_000 }).catch(
          () => undefined,
        )
      } catch {
        
      }
    }

    const exited = await Promise.race([
      new Promise<boolean>((resolve) => proc.once('exit', () => resolve(true))),
      new Promise<boolean>((resolve) => setTimeout(() => resolve(false), GRACEFUL_SHUTDOWN_MS)),
    ])

    if (!exited) {
      this.pushLog('[desktop] 优雅退出超时，强制结束进程树', 'stdout')
      
      
      logDesktop(`[backend] 优雅退出超时（${GRACEFUL_SHUTDOWN_MS}ms），强制结束进程树`)
      await killProcessTree(proc)
    }
    this.secrets?.cleanupTempFile()
    this.proc = null
    this.info = null
  }

  
  
  
  private emitStatus(state: BackendState, message: string): void {
    this.onStatus?.({ state, message, restarts: this.restarts })
  }

  private pushLog(chunk: string, stream: 'stdout' | 'stderr'): void {
    for (const raw of chunk.split(/\r?\n/)) {
      const line = raw.trim()
      if (!line) continue
      this.logBuffer.push(`[${stream}] ${line}`)
      if (this.logBuffer.length > 500) this.logBuffer.shift()
      this.onLog?.(line, stream)
    }
  }
}
