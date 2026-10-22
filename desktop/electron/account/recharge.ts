

















import { logDesktop } from '../desktop-log'
import * as api from './api'
import { parseAmount } from './amount'
import type { AccountLine } from '../../shared/bridge'


const MAX_RENEWALS = 3
const DEFAULT_WINDOW_SECONDS = 45
const DEFAULT_POLL_SECONDS = 15

export interface RechargeHost {
  
  line(): AccountLine
  
  auth(): api.AuthContext
  
  balance(): string
  
  applyBalance(balance: string): void
  
  onIncrease(): void
  
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
