/**
 * Python 核心进程的守护者。
 *
 * 职责：
 *  1. 解析可执行文件路径（开发环境用 venv 里的 python，生产环境用 PyInstaller 产物）；
 *  2. spawn 子进程并通过 **stdout 握手** 获取实际监听端口与本地令牌；
 *  3. 崩溃后自动重启（最多 3 次），并把状态上报给渲染层；
 *  4. 退出时先调 /v1/shutdown 优雅关闭，超时再强杀，避免留下僵尸进程。
 */
import { spawn, type ChildProcess } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

/**
 * 结束核心进程，**连同它拉起的子进程树**。
 *
 * 原先只有一句 `proc.kill('SIGKILL')`。在 Windows 上它等价于对**单个 PID**
 * 调 TerminateProcess —— 而核心自己拉起了一串 MCP Server（多是 `npx` 起的
 * node 进程）。父进程被杀之后它们**不会**跟着退出：
 *
 * - 继续占着内存和端口；
 * - 下次启动核心会再拉一遍，于是每强杀一次就多留一批；
 * - 用户看不到任何异常，只觉得"越用越卡、端口莫名被占"。
 *
 * `taskkill /T` 是 Windows 自带的按进程树终止，不需要任何额外依赖。
 *
 * **必须先杀树、再兜底杀自己**：Windows 上父进程一旦先死，子进程会被重新
 * 挂到别处，`taskkill /PID <父> /T` 那时就找不到它们了。
 */
async function killProcessTree(proc: ChildProcess): Promise<void> {
  const pid = proc.pid
  if (pid === undefined) return

  if (process.platform === 'win32') {
    await new Promise<void>((resolve) => {
      // 用 spawn 而不是 exec：少一层 shell，也就少一类转义问题
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
      // ⚠️ **必须带兜底超时**（第 87 批，M-31）：`taskkill` 被安全软件 / EDR 挂住时
      // 既不 close 也不 error，`stop()` 就永远不落地 → `app.quit()` 永不执行 ——
      // 而托盘模式下的「退出」在用户看来就是**完全没反应**，只能用任务管理器强杀。
      // 5 秒足够杀掉一棵进程树；超时就放弃等待，下面的兜底补刀仍会执行。
      const timer = setTimeout(() => {
        try {
          killer.kill()
        } catch {
          /* 已经退出了 */
        }
        finish()
      }, 5_000)
      killer.on('close', () => {
        clearTimeout(timer)
        finish()
      })
      // taskkill 本身起不来（例如被安全软件拦了）也要放行，
      // 否则 stop() 会永远卡在这一步
      killer.on('error', () => {
        clearTimeout(timer)
        finish()
      })
    })
  }

  // 兜底：taskkill 可能失败（进程刚好自己退了、权限不够、或是非 Windows）。
  // 再对核心自己补一刀，保证 stop() 一定有确定结果。
  try {
    proc.kill('SIGKILL')
  } catch {
    /* 已经退出了 */
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
/**
 * 连续崩溃的计数**只有在上次就绪之后稳定跑了这么久**才允许清零。
 *
 * 30s 的依据：正常启动到就绪约 1~3s，之后只要核心没毛病就不会在 30s 内退出；
 * 而"数据目录不可写 / 依赖缺失 / 端口冲突"这类会让人一直重启的故障，
 * 典型表现正是"起来几秒又挂"。
 */
const STABLE_RUN_MS = 30_000
const GRACEFUL_SHUTDOWN_MS = 3_000
/**
 * 调核心的默认超时。
 *
 * 这几条都是**本机回环**调用，正常都是毫秒级；给上限只为不出现
 * "核心半死（监听着但不应答）时这里永远挂着"。`/v1/shutdown` 自己传更短的值。
 */
const CORE_FETCH_TIMEOUT_MS = 20_000

/**
 * 调核心的**唯一入口**：统一注入 `baseUrl` 与 `X-Local-Token`。
 *
 * ⚠️ 为什么要收拢（第 86 批 B 组，M-18）：这层"已鉴权的核心调用"原来在**四个**地方
 * 各写一遍（`/v1/shutdown`、`/v1/skill-secrets`、`/v1/client/session`、`/v1/files`），
 * 各自拼 header、各自决定超时 —— 其中两条**完全没有超时**。
 * 而核心每次重启都会**换端口与令牌**：哪天要给这层加超时 / 重试 / 统一的错误上报，
 * 漏掉一处，那条路径就会静默地打向死地址，表现只是"某个功能偶尔没反应"。
 */
export async function coreFetch(
  info: Pick<BackendInfo, 'baseUrl' | 'token'>,
  path: string,
  init: RequestInit & { timeoutMs?: number } = {},
): Promise<Response> {
  const { timeoutMs = CORE_FETCH_TIMEOUT_MS, headers, signal, ...rest } = init
  const controller = new AbortController()
  const timer = timeoutMs > 0 ? setTimeout(() => controller.abort(), timeoutMs) : null
  // 调用方自带的 signal 也要能取消（例如窗口关掉时不再等）
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
  /**
   * 上次握手成功（就绪）的时刻；0 = 还没就绪过。
   *
   * ⚠️ 它是"这次崩溃算不算新的一轮"的唯一依据。**不能在握手时直接清零 `restarts`**：
   * `settled` 是单次启动的局部变量，而"启动 → 握手成功 → 立刻崩溃"这个循环每次都会
   * 走到握手那一行 —— 每轮清零会让 `restarts >= MAX_RESTARTS` 永远不成立，
   * 退避时间也恒为 `1000 * 1`，于是核心"起来就挂"时被**无限重启**。
   */
  private readyAt = 0
  private stopping = false
  private starting: Promise<BackendInfo> | null = null
  private readonly logBuffer: string[] = []

  onStatus?: (status: BackendStatus) => void
  onLog?: (line: string, stream: 'stdout' | 'stderr') => void

  constructor(
    private readonly dataDir: string,
    /** 密钥存储。传了它之后核心才会拿到 AGENT_SECRETS_FILE（见 secrets.ts 的说明） */
    private readonly secrets?: SecretsStore,
    /**
     * **用户给技能的密钥**存储（与上面那份完全独立）。
     *
     * ⚠️ 两条链路各有各的临时文件与注入变量：`AGENT_SECRETS_FILE` 给模型/MCP 用，
     * `AGENT_SKILL_SECRETS_FILE` 给 `{{secret:名字}}` 用。
     * 合成一个文件的话，核心那边两个读取器会互相抢着删（都是"读完即删"）。
     */
    private readonly skillSecrets?: SkillSecretsStore,
  ) {}

  get current(): BackendInfo | null {
    return this.info
  }

  /**
   * 是否已有子进程在跑（可能还没完成握手）。
   *
   * 退出流程必须用这个而不是 ``current``：启动途中（已 spawn、未握手）退出时
   * ``current`` 还是 null，只看它会把 Python 进程遗留在后台。
   */
  get hasProcess(): boolean {
    return this.proc !== null
  }

  get logs(): string[] {
    return this.logBuffer.slice(-200)
  }

  // ------------------------------------------------------------------ //
  // 路径解析
  // ------------------------------------------------------------------ //
  private buildLaunchSpec(): LaunchSpec {
    if (app.isPackaged) {
      // 生产环境：PyInstaller 产物放在 resources/agent-core/ 下
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

    // 开发环境：仓库内的 core 目录 + venv（__dirname = desktop/dist-electron/electron）
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

  // ------------------------------------------------------------------ //
  // 启动
  // ------------------------------------------------------------------ //
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

      // 密钥走一次性临时文件交接：环境变量会被核心进程再传给 MCP Server，
      // 等于把 Key 漏给第三方进程；传路径则只有核心知道，且它读完即删。
      let secretsFile: string | undefined
      try {
        secretsFile = this.secrets?.materialize()
      } catch (error) {
        console.error('[desktop] 密钥交接文件写入失败，本次将以空密钥启动:', error)
      }

      // 用户给技能的密钥走**另一份**临时文件（同一个交接机制，不同变量）。
      // ⚠️ 不能与上面合成一份：核心那边两个读取器都是"读完即删"，
      // 共用文件会让后读到的那个永远读到空。
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
          // 强制 UTF-8，否则 Windows 下中文日志会变成乱码
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
        // ⚠️ 同时落持久日志（第 88 批，M-26）：`pushLog` 只进 500 行内存环形缓冲，
        // 进程一退就没了 —— 而"核心起不来 / 莫名重启"恰恰是偶发、无法复现、
        // 必须靠**事发当时留下的东西**才能查清的那类问题。
        logDesktop(`[backend] 启动超时：${START_TIMEOUT_MS}ms 内未收到握手信息，终止进程`)
        this.emitStatus('failed', '智能体核心启动超时，请查看日志。')
        proc.kill()
        reject(new Error('后端启动超时'))
      }, START_TIMEOUT_MS)

      proc.stdout?.setEncoding('utf-8')
      proc.stdout?.on('data', (chunk: string) => {
        this.pushLog(chunk, 'stdout')
        stdoutBuffer += chunk

        // 逐行扫描握手信息；握手之后 stdout 基本不再有输出
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
              // 只记时刻，**不清零** `restarts`（理由见 `readyAt` 的说明）；
              // 是否清零交给 `scheduleRestart()` 按"稳定运行了多久"判定。
              this.readyAt = Date.now()
              this.emitStatus('ready', '智能体核心已就绪')
              // 成功也要留一行（第 88 批，M-26）：否则桌面日志里**只有失败**，
              // 事后无法区分"这次到底启动成功没有"——而"启动成功"是判断
              // "偶发打不开"的第一分界线。
              logDesktop(`[backend] 核心已就绪 baseUrl=${this.info?.baseUrl ?? '?'}`)
              // 核心读完密钥文件会立即删掉；这里只是它没删成时的兜底
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
        // 启动失败时核心没机会读走密钥文件，必须由我们清理
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
        // 退出原因必须落盘（第 88 批，M-26）：这是"核心为什么没了"的**原始证据**，
        // 而它以前只活在内存里。带上 stopping/是否已就绪/已重启几次，
        // 这三样决定了它是"正常退出"还是"崩溃循环"。
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
    // 只有"上次就绪之后稳定跑了够久"才把连续失败计数清零。
    // 少了这一步，"起来就挂"每轮都被当成新问题，MAX_RESTARTS 形同虚设（见 `readyAt`）。
    if (this.readyAt && Date.now() - this.readyAt >= STABLE_RUN_MS) {
      this.restarts = 0
    }
    this.readyAt = 0
    if (this.restarts >= MAX_RESTARTS) {
      this.emitStatus('failed', `智能体核心反复异常退出，已停止自动重启（${MAX_RESTARTS} 次）。`)
      // 放弃自动重启是**用户会看到的现象**（界面停在失败页），必须留痕：
      // 否则事后只能看到"核心退出了"，看不出"我们为什么不再救它"（第 88 批，M-26）。
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
      // start() 内部已经把失败状态上报过了
    }
  }

  async restart(): Promise<BackendInfo> {
    await this.stop()
    this.stopping = false
    // 这是用户**主动**要求重启（启动失败页的「重新启动」），属于新的一轮：
    // 计数与就绪时刻都清掉，否则用户点几次就把自动重启的额度用光了。
    this.restarts = 0
    this.readyAt = 0
    return this.start()
  }

  // ------------------------------------------------------------------ //
  // 停止
  // ------------------------------------------------------------------ //
  async stop(): Promise<void> {
    this.stopping = true
    const proc = this.proc
    const info = this.info
    if (!proc) return

    // 先请求优雅退出，让 Python 侧有机会关闭 MCP 子进程、flush 日志
    if (info) {
      try {
        // 1 秒就够（本机回环），超了说明核心已经不正常 —— 下面还有强杀兜底
        await coreFetch(info, '/v1/shutdown', { method: 'POST', timeoutMs: 1_000 }).catch(
          () => undefined,
        )
      } catch {
        // 忽略：下面还有强杀兜底
      }
    }

    const exited = await Promise.race([
      new Promise<boolean>((resolve) => proc.once('exit', () => resolve(true))),
      new Promise<boolean>((resolve) => setTimeout(() => resolve(false), GRACEFUL_SHUTDOWN_MS)),
    ])

    if (!exited) {
      this.pushLog('[desktop] 优雅退出超时，强制结束进程树', 'stdout')
      // 走这条路说明核心没理 `POST /v1/shutdown`（第 88 批，M-26）——
      // 是"卡死"还是"正常但要慢一点"，只有日志能说话。
      logDesktop(`[backend] 优雅退出超时（${GRACEFUL_SHUTDOWN_MS}ms），强制结束进程树`)
      await killProcessTree(proc)
    }
    this.secrets?.cleanupTempFile()
    this.proc = null
    this.info = null
  }

  // ------------------------------------------------------------------ //
  // 内部工具
  // ------------------------------------------------------------------ //
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
