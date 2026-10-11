/**
 * 充值盯单（文档 §8）。
 *
 * 流程是后端规定的，客户端只有一件事要照做：**别自己去查链上**，
 * 而是"让后端盯住这个地址 → 自己按节奏拉余额 → 窗口到期还在页面上就再盯一次"。
 *
 * ## 为什么用一个 1 秒的心跳，而不是两个定时器
 *
 * 界面上有一个倒计时（"还剩 32 秒"），余额轮询是 15 秒一次，续盯是 45 秒一次。
 * 拆成三个定时器要自己维护它们之间的相位；合成一个 1 秒的心跳之后，
 * 所有时间判断都在同一处、同一时刻发生，倒计时也不会出现跳变。
 *
 * ## 为什么必须能被停掉
 *
 * 用户离开充值区之后还在每 15 秒打一次接口，是"看不见的流量"，而且
 * 一到账我们会把它当成"用户正在充"来处理。所以 `stop()` 由渲染层在离开时调用。
 * 另外续盯有次数上限（默认 3 轮）：用户把页面开着去吃饭，不该让请求一直打下去。
 */
import { logDesktop } from '../desktop-log'
import * as api from './api'
import { parseAmount } from './amount'
import type { AccountLine } from '../../shared/bridge'

/** 续盯的最多轮数（文档 §8 的"循环 2–3 次"） */
const MAX_RENEWALS = 3
const DEFAULT_WINDOW_SECONDS = 45
const DEFAULT_POLL_SECONDS = 15

export interface RechargeHost {
  /** 当前线路 */
  line(): AccountLine
  /** 当前账号的请求凭据 */
  auth(): api.AuthContext
  /** 界面上的余额（用来判断有没有变大） */
  balance(): string
  /** 拉到新余额后把账号信息写回去 */
  applyBalance(balance: string): void
  /** 检测到余额变大 */
  onIncrease(): void
  /** 让界面重画（倒计时每跳一秒都要） */
  publish(): void
}

export class RechargeWatcher {
  private timer: NodeJS.Timeout | null = null
  private until = 0
  private nextPollAt = 0
  private pollMs = DEFAULT_POLL_SECONDS * 1000
  private renewals = 0
  private busy = false

  constructor(private readonly host: RechargeHost) {}

  get active(): boolean {
    return this.timer !== null
  }

  get secondsLeft(): number {
    if (!this.timer || !this.until) return 0
    return Math.max(0, Math.round((this.until - Date.now()) / 1000))
  }

  /** 开始盯（第一次与"续盯"都走这里）。 */
  start(windowSeconds?: number, pollSeconds?: number): void {
    const window = windowSeconds && windowSeconds > 0 ? windowSeconds : DEFAULT_WINDOW_SECONDS
    this.pollMs = (pollSeconds && pollSeconds > 0 ? pollSeconds : DEFAULT_POLL_SECONDS) * 1000
    this.until = Date.now() + window * 1000
    this.nextPollAt = Date.now() + this.pollMs
    if (!this.timer) this.timer = setInterval(() => void this.tick(), 1000)
    logDesktop(`[account] 开始盯充值，窗口 ${window}s，轮询 ${this.pollMs / 1000}s`)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
    this.until = 0
    this.renewals = 0
    this.busy = false
  }

  private async tick(): Promise<void> {
    if (!this.timer) return
    if (this.until && Date.now() >= this.until) {
      // 窗口到期：用户还停在页面上（否则 stop() 早就被调过了）→ 续盯
      if (this.renewals < MAX_RENEWALS) {
        this.renewals += 1
        await this.renew()
      } else {
        logDesktop('[account] 续盯次数已到上限，停止盯单')
        this.stop()
      }
      this.host.publish()
      return
    }
    if (Date.now() >= this.nextPollAt) await this.poll()
    this.host.publish()
  }

  private async renew(): Promise<void> {
    try {
      const result = await api.watchRecharge(this.host.line(), this.host.auth())
      this.until = Date.now() + (result.window_seconds || DEFAULT_WINDOW_SECONDS) * 1000
      this.nextPollAt = Date.now() + this.pollMs
    } catch (error) {
      // 续盯失败不是"充值失败"，只记日志：这一轮确实没人盯着了，
      // 但用户重新点一次「开始盯单」立刻就能恢复
      logDesktop(`[account] 续盯失败：${error instanceof Error ? error.message : String(error)}`)
      this.stop()
    }
  }

  private async poll(): Promise<void> {
    if (this.busy) return
    this.busy = true
    this.nextPollAt = Date.now() + this.pollMs
    const before = parseAmount(this.host.balance())
    try {
      const { user } = await api.fetchAccount(this.host.line(), this.host.auth())
      if (parseAmount(user.token_balance) > before) this.host.onIncrease()
      this.host.applyBalance(user.token_balance)
    } catch (error) {
      logDesktop(`[account] 余额轮询失败：${error instanceof Error ? error.message : String(error)}`)
    } finally {
      this.busy = false
    }
  }
}
