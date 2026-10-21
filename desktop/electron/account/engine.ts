















import os from 'node:os'

import type {
  AccountActionResult,
  AccountCommission,
  AccountLine,
  AccountSnapshot,
  AccountUser,
  PayPalConfig,
  PayPalNotice,
  PayPalOrderState,
  PayPalOrderStatus,
  PayPalResult,
  RedeemOutcome,
  WxOrderState,
} from '../../shared/bridge'
import { logDesktop } from '../desktop-log'
import * as api from './api'
import { AccountApiError } from './api'
import { collectDeviceInfo, isDeviceUsable, type DeviceInfo } from './device'
import {
  ACCOUNT_LINES,
  FULL_ROUNDS,
  QUICK_ROUNDS,
  decideLine,
  isStale,
  measureLines,
  probeOnce,
} from './lines'
import { RechargeWatcher } from './recharge'
import { AccountSecretStore } from './secure'
import { AccountStore, type AccountData } from './store'


const RETRY_INTERVAL_MS = 60_000

const NETWORK_PROBE_TIMEOUT_MS = 1_500

const ACCOUNT_NAME = /^[A-Za-z0-9_]{3,32}$/
const MIN_PASSWORD = 6

const WX_POLL_MS = 2_500
const WX_MAX_YUAN = 50_000

const PAYPAL_POLL_MS = 3_000







const PAYPAL_DEFAULT_EXPIRES_SECONDS = 1_800







const PAYPAL_DEFAULT_MIN = 1
const PAYPAL_DEFAULT_MAX = 100

export type SnapshotListener = (snapshot: AccountSnapshot) => void





export interface PaypalCheckoutHost {
  open(url: string): void
  close(): void
}










export interface SessionSync {
  push(token: string): void
}

function toApiError(error: unknown): AccountApiError {
  if (error instanceof AccountApiError) return error
  return new AccountApiError('network', error instanceof Error ? error.message : String(error))
}


function normalizePaypalStatus(raw: string): PayPalOrderStatus {
  const value = raw.trim().toLowerCase()
  if (value === 'paid' || value === 'success' || value === 'completed') return 'PAID'
  if (value === 'expired') return 'EXPIRED'
  if (value === 'cancelled' || value === 'canceled') return 'CANCELLED'
  if (value === 'failed' || value === 'fail') return 'FAILED'
  return 'PENDING'
}







function paypalExpiresSeconds(raw: unknown): number {
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) return PAYPAL_DEFAULT_EXPIRES_SECONDS
  return Math.round(value)
}







function shortCt(ct: string): string {
  return ct ? `ct=${ct.slice(0, 8)}…` : 'ct=（空）'
}










function paypalErrorNotice(error: AccountApiError): PayPalNotice {
  const base = paypalBaseNotice(error)
  if (error.status > 0 && error.message && !base.message.includes(error.message)) {
    return { tone: base.tone, message: `${base.message}（服务端原因：${error.message}）` }
  }
  return base
}

function paypalBaseNotice(error: AccountApiError): PayPalNotice {
  switch (error.status) {
    case 503:
      return { tone: 'danger', message: 'PayPal 通道正在开通中，暂时无法充值。' }
    case 401:
      return { tone: 'warning', message: '登录状态已失效，请重新登录后再试。' }
    case 400:
      
      
      
      
      
      
      return {
        tone: 'danger',
        message: error.message || '这笔充值请求被拒绝了，请重新发起或联系客服。',
      }
    case 404:
      return { tone: 'warning', message: '这笔订单已不存在，请重新发起。' }
    case 403:
    case 409:
      return { tone: 'danger', message: '本次充值被拒绝，请联系客服处理。' }
    case 502:
      return { tone: 'warning', message: '支付网关正在同步，请稍候…' }
    default:
      return { tone: 'danger', message: error.message }
  }
}

export class AccountEngine {
  private readonly store = new AccountStore()
  private readonly secrets = new AccountSecretStore()
  private data: AccountData
  private recharge: RechargeWatcher

  private phase: AccountSnapshot['phase'] = 'idle'
  private message = '正在准备账号…'
  private deviceUsable = true
  private offline = false
  private offlinePrompt = false
  private offlineNotified = false
  
  private checksSkipped = false
  private balanceIncreasedAt: number | null = null
  private retryTimer: NodeJS.Timeout | null = null
  
  private busy: Promise<unknown> = Promise.resolve()
  private lastPublished = ''
  
  private commission: AccountCommission | null = null
  





  private commissionError = ''
  
  private wxOrder: WxOrderState | null = null
  private wxExpiresAt = 0
  private wxTimer: NodeJS.Timeout | null = null
  
  private paypalConfig: PayPalConfig | null = null
  
  private paypalOrder: PayPalOrderState | null = null
  
  private paypalExpiresAt = 0
  private paypalTimer: NodeJS.Timeout | null = null
  
  private paypalNotice: PayPalNotice | null = null

  constructor(
    private readonly notify: SnapshotListener,
    
    private readonly paypalHost?: PaypalCheckoutHost,
    
    private readonly sessionSync?: SessionSync,
  ) {
    this.data = this.store.load()
    if (this.data.deviceInfo) this.deviceUsable = isDeviceUsable(this.data.deviceInfo)
    this.recharge = new RechargeWatcher({
      line: () => this.currentLine(),
      auth: () => this.authFor(this.currentUser()),
      balance: () => this.currentUser()?.token_balance ?? '0.000000',
      applyBalance: (balance) => {
        const current = this.currentUser()
        if (current) this.updateUser(current.id, { token_balance: balance })
      },
      onIncrease: () => {
        this.balanceIncreasedAt = Date.now()
        
        void this.refreshCommission()
      },
      publish: () => this.publish(),
    })
  }

  
  
  
  
  start(): void {
    this.publish()
    
    
    
    if (process.env.SOULMATE_ACCOUNT_DISABLED === '1') {
      logDesktop('[account] 已按 SOULMATE_ACCOUNT_DISABLED 跳过账号首启')
      return
    }
    this.scheduleRetry()
    void this.exclusive(() => this.boot()).catch(() => undefined)
  }

  stop(): void {
    if (this.retryTimer) clearInterval(this.retryTimer)
    this.retryTimer = null
    this.recharge.stop()
    this.stopWxPolling()
    this.stopPaypalPolling()
    
    this.paypalHost?.close()
  }

  snapshot(): AccountSnapshot {
    return {
      phase: this.phase,
      message: this.message,
      deviceUsable: this.deviceUsable,
      offline: this.offline,
      offlinePrompt: this.offlinePrompt,
      accounts: this.data.accounts,
      currentId: this.currentUser()?.id ?? null,
      hasDeviceSecret: this.secrets.has('device_secret'),
      loggedIn: this.secrets.has('session_token'),
      rate: this.data.rate,
      line: this.data.line,
      watching: this.recharge.active,
      watchSecondsLeft: this.recharge.secondsLeft,
      balanceIncreasedAt: this.balanceIncreasedAt,
      commission: this.commission,
      
      commissionError: this.commissionError,
      wxOrder: this.wxOrder,
      paypalConfig: this.paypalConfig,
      paypalOrder: this.paypalOrder,
      paypalNotice: this.paypalNotice,
    }
  }

  
  async refresh(): Promise<AccountSnapshot> {
    await this.exclusive(async () => {
      if (!this.deviceUsable) return
      if (this.offline) {
        if (!(await this.checkNetwork())) return
        this.offline = false
      }
      await this.runAccountStages()
      await this.flushPending()
    }).catch(() => undefined)
    return this.snapshot()
  }

  
  
  
  async setAccountLine(line: AccountLine): Promise<AccountSnapshot> {
    const measurements = this.data.line?.measurements ?? {}
    this.data = this.store.patch({
      line: { preferred: line, measurements, updatedAt: Date.now(), manual: true },
    })
    
    this.resetPaymentState()
    logDesktop(`[account] 用户手动切换线路到 ${line}`)
    return this.publish()
  }

  
  async reprobeLines(): Promise<AccountSnapshot> {
    await this.exclusive(async () => {
      if (!this.deviceUsable) return
      await this.probeLinesIfNeeded(true)
    }).catch(() => undefined)
    return this.snapshot()
  }

  
  async loginAccount(account: string, password: string): Promise<AccountActionResult> {
    return this.action(async () => {
      const name = account.trim()
      if (!name) throw new AccountApiError('bad-request', '请输入账号。')
      await this.doLogin(name, password)
      await this.pullAccountInfo()
    })
  }

  async switchAccount(id: number, password: string): Promise<AccountActionResult> {
    return this.action(async () => {
      const target = this.data.accounts.find((user) => user.id === id)
      if (!target) throw new AccountApiError('no-account', '这个账号不在本机列表里。')
      if (this.currentUser()?.id === target.id && this.secrets.has('session_token')) return
      
      
      if (target.has_password && !password) {
        throw new AccountApiError('unauthorized', '请输入该账号的密码。')
      }
      if (!target.has_password && !target.is_primary && !password) {
        throw new AccountApiError(
          'unauthorized',
          '该账号尚未设置密码，无法切换登录，请先在它的绑定设备上设置密码。',
        )
      }
      await this.doLogin(target.account, password)
      await this.pullAccountInfo()
    })
  }

  async renameAccount(name: string, password: string): Promise<AccountActionResult> {
    return this.action(async () => {
      const trimmed = name.trim()
      if (!ACCOUNT_NAME.test(trimmed)) {
        throw new AccountApiError('bad-request', '账号名必须是 3–32 位字母、数字或下划线。')
      }
      const current = this.requireUser()
      
      await this.healDeviceKeyIfMissing()
      const { user } = await api.renameAccount(this.currentLine(), this.deviceAuth(), {
        account: current.account,
        newAccount: trimmed,
        password,
      })
      this.data = this.store.patch({ accounts: this.mergeUsers([user]) })
    })
  }

  async setAccountPassword(next: string, old: string): Promise<AccountActionResult> {
    return this.action(async () => {
      if (next.length < MIN_PASSWORD) throw new AccountApiError('bad-request', '密码至少 6 位。')
      const current = this.requireUser()
      if (current.has_password && !old) throw new AccountApiError('bad-request', '请输入旧密码。')
      
      await this.healDeviceKeyIfMissing()
      const { user } = await api.setPassword(this.currentLine(), this.deviceAuth(), {
        account: current.account,
        newPassword: next,
        oldPassword: current.has_password ? old : undefined,
      })
      this.data = this.store.patch({ accounts: this.mergeUsers([user]) })
    })
  }

  async recoverAccount(account: string, next: string): Promise<AccountActionResult> {
    return this.action(async () => {
      const name = account.trim()
      if (!name) throw new AccountApiError('bad-request', '请输入要找回的账号。')
      if (next.length < MIN_PASSWORD) throw new AccountApiError('bad-request', '密码至少 6 位。')
      await api.recoverAccount(this.currentLine(), {
        account: name,
        deviceInfo: this.requireDeviceInfo(),
        newPassword: next,
      })
      logDesktop(`[account] 账号 ${name} 已通过设备指纹重置密码`)
    })
  }

  async submitInviteCode(code: string): Promise<AccountActionResult> {
    return this.action(async () => {
      const trimmed = code.trim()
      if (!trimmed) throw new AccountApiError('bad-request', '请输入邀请码。')
      if (this.offline) {
        
        this.store.addPending({ kind: 'invite', code: trimmed, at: Date.now() })
        throw new AccountApiError(
          'network',
          '当前网络不可用，已记下这个邀请码，联网后会自动提交。',
        )
      }
      await this.applyInvite(trimmed)
    })
  }

  








  async redeem(code: string): Promise<RedeemOutcome> {
    const trimmed = code.trim()
    if (!trimmed) {
      return { ok: false, message: '', error: '请填写兑换码。', snapshot: this.publish() }
    }
    try {
      const message = await this.exclusive(async () => {
        const current = this.requireUser()
        const result = await api.redeemCode(this.currentLine(), this.authFor(current), trimmed)
        
        if (result.user?.token_balance) {
          this.updateUser(current.id, { token_balance: result.user.token_balance })
        }
        logDesktop(`[account] 兑换码已核销，获得 ${result.token_amount} Token`)
        return result.message
      })
      return { ok: true, message, error: '', snapshot: this.publish() }
    } catch (error) {
      const apiError = toApiError(error)
      logDesktop(`[account] 兑换码失败：${apiError.code} ${apiError.message}`)
      return { ok: false, message: '', error: apiError.message, snapshot: this.publish() }
    }
  }

  async watchRecharge(): Promise<AccountActionResult> {
    return this.action(async () => {
      const current = this.requireUser()
      const result = await api.watchRecharge(this.currentLine(), this.authFor(current))
      if (result.address && !current.tron_address) {
        this.updateUser(current.id, { tron_address: result.address })
      }
      this.recharge.start(result.window_seconds, result.balance_poll_seconds)
    })
  }

  async stopRechargeWatch(): Promise<AccountSnapshot> {
    this.recharge.stop()
    return this.publish()
  }

  async answerOfflinePrompt(mode: 'continue' | 'skip'): Promise<void> {
    this.offlinePrompt = false
    if (mode === 'skip') {
      this.checksSkipped = true
      if (this.retryTimer) clearInterval(this.retryTimer)
      this.retryTimer = null
      logDesktop('[account] 用户选择跳过联网检测，本次运行不再自动重试')
    }
    this.publish()
  }

  
  
  
  





  async getCommission(): Promise<AccountActionResult> {
    return this.action(async () => {
      
      
      await this.healDeviceKeyIfMissing()
      await this.pullCommission()
    })
  }

  
  async createWxRecharge(amountYuan: number): Promise<AccountActionResult> {
    return this.action(async () => {
      if (!Number.isInteger(amountYuan) || amountYuan < 1 || amountYuan > WX_MAX_YUAN) {
        throw new AccountApiError('bad-request', `充值金额必须是 1~${WX_MAX_YUAN} 的整数（元）。`)
      }
      if (this.currentLine() !== 'cn') {
        throw new AccountApiError('forbidden', '微信充值仅在大陆线路开放，请切换到大陆线路。')
      }
      
      if (
        this.wxOrder &&
        (this.wxOrder.status === 'CREATING' || this.wxOrder.status === 'NOTPAY') &&
        this.wxOrder.amount_yuan === amountYuan &&
        this.wxExpiresAt > Date.now()
      ) {
        return
      }
      const current = this.requireUser()
      this.stopWxPolling()
      const result = await api.wxCreateOrder(this.currentLine(), this.authFor(current), amountYuan)
      this.wxOrder = {
        order_no: result.order_no,
        amount_yuan: result.amount_yuan,
        token_amount: result.token_amount,
        status: 'CREATING',
        code_url: result.code_url,
        countdown_seconds: result.expire_seconds,
      }
      this.wxExpiresAt = Date.now() + result.expire_seconds * 1000
      this.startWxPolling()
      logDesktop(`[account] 微信下单 ${result.order_no} 金额 ${result.amount_yuan} 元`)
      this.publish()
    })
  }

  
  async cancelWxRecharge(): Promise<AccountSnapshot> {
    this.stopWxPolling()
    this.wxOrder = null
    this.wxExpiresAt = 0
    return this.publish()
  }

  
  
  

  





  private paypalLineGate(): PayPalNotice | null {
    if (this.currentLine() === 'seoul') return null
    return { tone: 'danger', message: 'PayPal 充值仅在首尔线路开放，请先切换到首尔线路。' }
  }

  






  async loadPaypalConfig(): Promise<PayPalResult> {
    const gate = this.paypalLineGate()
    if (gate) {
      this.paypalNotice = gate
      return { ok: false, error: gate.message, notice: gate, snapshot: this.publish() }
    }
    try {
      const config = await this.exclusive(async () => {
        const current = this.requireUser()
        return api.paypalConfig(this.currentLine(), this.authFor(current))
      })
      
      
      
      
      
      const min = Number(config.min)
      const max = Number(config.max_quantity ?? config.max)
      const unitPrice = Number(config.unit_tokens ?? config.unit_price)
      const unitUsd = Number(config.unit_usd)
      const usable = (value: number) => Number.isFinite(value) && value > 0
      this.paypalConfig = {
        unit_price: usable(unitPrice) ? unitPrice : 0,
        unit_usd: usable(unitUsd) ? unitUsd : 0,
        min: usable(min) ? min : PAYPAL_DEFAULT_MIN,
        max: usable(max) ? max : PAYPAL_DEFAULT_MAX,
        client_id: String(config.client_id ?? ''),
        mode: String(config.mode ?? ''),
        currency: String(config.currency ?? 'USD'),
      }
      this.paypalNotice = null
      logDesktop(
        `[account] PayPal 配置就绪（${this.paypalConfig.unit_usd} USD/份 = ` +
          `${this.paypalConfig.unit_price} Token，${this.paypalConfig.min}-${this.paypalConfig.max} 份）`,
      )
      return { ok: true, snapshot: this.publish() }
    } catch (error) {
      const apiError = toApiError(error)
      const notice = paypalErrorNotice(apiError)
      logDesktop(`[account] PayPal 配置取不到：${apiError.code} ${apiError.message}`)
      this.paypalNotice = notice
      return { ok: false, error: apiError.message, notice, snapshot: this.publish() }
    }
  }

  













  async createPaypalCheckout(quantity: number): Promise<PayPalResult> {
    const gate = this.paypalLineGate()
    if (gate) {
      this.paypalNotice = gate
      return { ok: false, error: gate.message, notice: gate, snapshot: this.publish() }
    }
    if (!this.paypalHost) {
      const notice: PayPalNotice = { tone: 'danger', message: '结账窗口不可用，请重启应用后再试。' }
      this.paypalNotice = notice
      return { ok: false, error: notice.message, notice, snapshot: this.publish() }
    }
    const min = this.paypalConfig?.min ?? PAYPAL_DEFAULT_MIN
    const max = this.paypalConfig?.max ?? PAYPAL_DEFAULT_MAX
    const safe = Math.min(max, Math.max(min, Math.round(Number(quantity) || min)))
    try {
      const result = await this.exclusive(async () => {
        const current = this.requireUser()
        return api.paypalSession(this.currentLine(), this.authFor(current), { quantity: safe })
      })
      
      const url = result.checkout_url || result.approve_url || ''
      const ct = String(result.ct ?? '').trim()
      if (!url || !ct) {
        
        const notice: PayPalNotice = { tone: 'danger', message: '后端没有返回结账地址，请稍后重试。' }
        this.paypalNotice = notice
        logDesktop(`[account] PayPal 建会话返回不完整（地址=${url ? '有' : '无'}，${shortCt(ct)}）`)
        return { ok: false, error: notice.message, notice, snapshot: this.publish() }
      }
      const expiresSeconds = paypalExpiresSeconds(result.expires_in)
      this.stopPaypalPolling()
      this.paypalOrder = {
        ct,
        quantity: safe,
        status: 'PENDING',
        countdown_seconds: expiresSeconds,
        expires_seconds: expiresSeconds,
      }
      this.paypalExpiresAt = Date.now() + expiresSeconds * 1000
      this.paypalNotice = null
      this.paypalHost.open(url)
      this.startPaypalPolling()
      logDesktop(`[account] PayPal 建会话成功（${safe} 份 / ${expiresSeconds}s），结账窗口已打开 ${shortCt(ct)}`)
      return { ok: true, snapshot: this.publish() }
    } catch (error) {
      const apiError = toApiError(error)
      const notice = paypalErrorNotice(apiError)
      logDesktop(`[account] PayPal 建会话失败：${apiError.code} ${apiError.message}`)
      this.paypalNotice = notice
      return { ok: false, error: apiError.message, notice, snapshot: this.publish() }
    }
  }

  
  async cancelPaypalCheckout(): Promise<AccountSnapshot> {
    this.stopPaypalPolling()
    this.paypalHost?.close()
    this.paypalOrder = null
    this.paypalExpiresAt = 0
    this.paypalNotice = null
    return this.publish()
  }

  






  dismissPaypalNotice(): AccountSnapshot {
    this.paypalNotice = null
    return this.publish()
  }

  





  handlePaypalWindowClosed(): void {
    const order = this.paypalOrder
    if (!order || order.status !== 'PENDING') return
    this.stopPaypalPolling()
    this.paypalOrder = null
    this.paypalExpiresAt = 0
    this.paypalNotice = { tone: 'warning', message: '结账窗口已关闭，本次充值未完成。' }
    this.publish()
  }

  private startPaypalPolling(): void {
    this.stopPaypalPolling()
    this.paypalTimer = setInterval(() => void this.paypalTick(), PAYPAL_POLL_MS)
  }

  private stopPaypalPolling(): void {
    if (this.paypalTimer) clearInterval(this.paypalTimer)
    this.paypalTimer = null
  }

  
  private async paypalTick(): Promise<void> {
    const order = this.paypalOrder
    if (!order) return
    if (Date.now() >= this.paypalExpiresAt) {
      this.stopPaypalPolling()
      this.paypalHost?.close()
      this.paypalOrder = { ...order, status: 'EXPIRED', countdown_seconds: 0 }
      
      
      this.paypalNotice = { tone: 'warning', message: '结账窗口已超时，请重新发起充值。' }
      this.publish()
      return
    }
    this.paypalOrder = {
      ...order,
      countdown_seconds: Math.max(0, Math.round((this.paypalExpiresAt - Date.now()) / 1000)),
    }
    this.publish()
    await this.paypalPoll()
  }

  





  private async paypalPoll(): Promise<void> {
    const order = this.paypalOrder
    if (!order || order.status !== 'PENDING') return
    const current = this.currentUser()
    if (!current) return
    try {
      const result = await api.paypalStatus(this.currentLine(), this.authFor(current), {
        ct: order.ct,
      })
      if (result.paid || result.already) {
        this.stopPaypalPolling()
        this.paypalHost?.close()
        this.paypalOrder = { ...order, status: 'PAID', countdown_seconds: 0 }
        this.paypalNotice = {
          tone: 'success',
          
          message: result.already ? '这笔充值已到账，余额已刷新。' : '支付成功，Token 已到账。',
        }
        this.balanceIncreasedAt = Date.now()
        logDesktop(
          `[account] PayPal 本次充值已到账（already=${result.already}，` +
            `+${result.token_amount ?? '?'} Token，${shortCt(order.ct)}）`,
        )
        try {
          await this.pullAccountInfo() 
          await this.refreshCommission() 
        } catch (error) {
          
          logDesktop(`[account] PayPal 到账后刷新余额失败：${toApiError(error).message}`)
        }
        this.publish()
        return
      }
      const status = normalizePaypalStatus(result.status)
      if (status === 'EXPIRED' || status === 'FAILED' || status === 'CANCELLED') {
        this.stopPaypalPolling()
        this.paypalHost?.close()
        this.paypalOrder = { ...order, status, countdown_seconds: 0 }
        this.paypalNotice =
          status === 'EXPIRED'
            ? { tone: 'warning', message: '这笔订单已过期，请重新发起充值。' }
            : { tone: 'danger', message: '这笔订单未能完成，请重新发起或联系客服。' }
        this.publish()
        return
      }
      this.paypalOrder = { ...order, status: 'PENDING' }
      this.publish()
    } catch (error) {
      const apiError = toApiError(error)
      logDesktop(`[account] PayPal 查单失败：${apiError.code} ${apiError.message}`)
      if (apiError.status === 502) return 
      this.stopPaypalPolling()
      this.paypalHost?.close()
      this.paypalNotice = paypalErrorNotice(apiError)
      if (apiError.status === 404) {
        
        this.paypalOrder = { ...order, status: 'EXPIRED', countdown_seconds: 0 }
      }
      this.publish()
    }
  }

  






  async withdrawRmb(payload: {
    amount: number
    zhifubao: string
    bank: string
  }): Promise<AccountActionResult> {
    return this.action(async () => {
      if (!Number.isFinite(payload.amount) || payload.amount <= 0) {
        throw new AccountApiError('bad-request', '请输入有效的提现金额。')
      }
      if (this.currentLine() !== 'cn') {
        throw new AccountApiError('forbidden', '人民币提现仅在大陆线路开放。')
      }
      const zhifubao = payload.zhifubao.trim()
      const bank = payload.bank.trim()
      const ready = this.commission?.rmb?.payee_ready
      let method: 'zhifubao' | 'bank'
      let payee = ''
      if (zhifubao) {
        method = 'zhifubao'
        payee = zhifubao
      } else if (bank) {
        method = 'bank'
        payee = bank
      } else if (ready?.zhifubao) {
        method = 'zhifubao'
      } else if (ready?.bank) {
        method = 'bank'
      } else {
        throw new AccountApiError('bad-request', '请先填写支付宝账号或银行卡号（有一个即可）。')
      }
      const current = this.requireUser()
      await api.withdrawRmb(this.currentLine(), this.authFor(current), {
        amount: payload.amount,
        method,
        payee,
      })
      logDesktop(`[account] 人民币提现申请 ${payload.amount} 元（${method}）`)
      await this.refreshCommission()
    })
  }

  
  async withdrawUsdt(payload: { amount: number; trc20_address: string }): Promise<AccountActionResult> {
    return this.action(async () => {
      if (!Number.isFinite(payload.amount) || payload.amount <= 0) {
        throw new AccountApiError('bad-request', '请输入有效的提现金额。')
      }
      if (this.currentLine() !== 'seoul') {
        throw new AccountApiError('forbidden', 'USDT 提现仅在国际线路开放。')
      }
      const address = payload.trc20_address.trim()
      if (!/^T[A-Za-z0-9]{33}$/.test(address)) {
        throw new AccountApiError('bad-request', 'TRC20 地址格式不正确（T 开头，共 34 位）。')
      }
      const current = this.requireUser()
      await api.withdrawUsdt(this.currentLine(), this.authFor(current), {
        amount: payload.amount,
        trc20_address: address,
      })
      logDesktop(`[account] USDT 提现申请 ${payload.amount}`)
      await this.refreshCommission()
    })
  }

  







  private async pullCommission(): Promise<void> {
    const current = this.currentUser()
    if (!current) return
    try {
      this.commission = await api.fetchCommission(this.currentLine(), this.authFor(current))
      this.commissionError = ''
    } catch (error) {
      this.commissionError = toApiError(error).message
      logDesktop(`[account] 佣金取不到：${this.commissionError}`)
      
      this.publish()
      throw error
    }
    this.publish()
  }

  
  private async refreshCommission(): Promise<void> {
    try {
      await this.pullCommission()
    } catch {
      
    }
  }

  
  private resetPaymentState(): void {
    this.stopWxPolling()
    this.wxOrder = null
    this.wxExpiresAt = 0
    
    this.stopPaypalPolling()
    this.paypalHost?.close()
    this.paypalOrder = null
    this.paypalExpiresAt = 0
    this.paypalConfig = null
    this.paypalNotice = null
    this.commission = null
    
    this.commissionError = ''
  }

  private startWxPolling(): void {
    this.stopWxPolling()
    this.wxTimer = setInterval(() => void this.wxTick(), WX_POLL_MS)
  }

  private stopWxPolling(): void {
    if (this.wxTimer) clearInterval(this.wxTimer)
    this.wxTimer = null
  }

  
  private async wxTick(): Promise<void> {
    if (!this.wxOrder) return
    
    
    if (this.wxExpiresAt && Date.now() >= this.wxExpiresAt) {
      this.stopWxPolling()
      this.wxOrder = { ...this.wxOrder, status: 'CLOSED', countdown_seconds: 0 }
      this.publish()
      return
    }
    this.wxOrder = {
      ...this.wxOrder,
      countdown_seconds: Math.max(0, Math.round((this.wxExpiresAt - Date.now()) / 1000)),
    }
    this.publish()
    await this.wxPoll()
  }

  private async wxPoll(): Promise<void> {
    const order = this.wxOrder
    if (!order || (order.status !== 'CREATING' && order.status !== 'NOTPAY')) return
    const current = this.currentUser()
    if (!current) return
    try {
      const result = await api.wxQueryOrder(this.currentLine(), this.authFor(current), order.order_no)
      if (result.status === 'SUCCESS') {
        this.stopWxPolling()
        this.wxOrder = { ...order, status: 'SUCCESS', token_amount: result.token_amount, countdown_seconds: 0 }
        this.balanceIncreasedAt = Date.now()
        logDesktop(`[account] 微信订单 ${order.order_no} 已到账`)
        await this.pullAccountInfo() 
        await this.refreshCommission() 
      } else if (result.status === 'CLOSED' || result.status === 'FAIL') {
        this.stopWxPolling()
        this.wxOrder = { ...order, status: result.status, countdown_seconds: 0 }
        this.publish()
      } else {
        this.wxOrder = { ...order, status: result.status }
        this.publish()
      }
    } catch (error) {
      const apiError = toApiError(error)
      logDesktop(`[account] 微信查单失败：${apiError.message}`)
      
      if (apiError.code === 'no-account') {
        this.stopWxPolling()
        this.wxOrder = { ...order, status: 'CLOSED', countdown_seconds: 0 }
        this.publish()
      }
    }
  }

  
  
  
  private async boot(): Promise<void> {
    
    
    this.publish()

    
    const info = await collectDeviceInfo(true)
    this.data = this.store.patch({ deviceInfo: info })
    if (!isDeviceUsable(info)) {
      this.deviceUsable = false
      this.setPhase('device-unusable', '无法识别本机设备，账号相关功能暂不可用。')
      logDesktop('[account] 设备主判据全空，账号功能不可用（不再重试）')
      return
    }
    this.deviceUsable = true

    
    this.setPhase('checking-network', '正在检查网络…')
    if (!(await this.checkNetwork())) {
      this.goOffline('当前网络不可用，账号相关功能暂不可用。')
      return
    }
    this.offline = false

    
    await this.runAccountStages(true)
    await this.flushPending()
    
    
    await this.healDeviceKeyIfMissing()
  }

  
  private async checkNetwork(): Promise<boolean> {
    
    const adapter = Object.values(os.networkInterfaces()).some((list) =>
      (list ?? []).some((item) => !item.internal && String(item.family) === 'IPv4'),
    )
    if (!adapter) {
      logDesktop('[account] 没有可用的网络适配器')
      return false
    }
    const preferred = this.currentLine()
    const order = [preferred, ...ACCOUNT_LINES.filter((line) => line !== preferred)]
    for (const line of order) {
      try {
        await probeOnce(api.baseFor(line), NETWORK_PROBE_TIMEOUT_MS)
        return true
      } catch {
        
      }
    }
    return false
  }

  private async runAccountStages(fullProbe = false): Promise<void> {
    try {
      await this.probeLinesIfNeeded(fullProbe)
      await this.lookupOrRegister()
      await this.pullAccountInfo()
      this.offline = false
      this.setPhase('ready', '账号已就绪。')
    } catch (error) {
      this.noteFailure(toApiError(error))
    }
  }

  






  private async probeLinesIfNeeded(force = false): Promise<void> {
    const previous = this.data.line
    const full = force || isStale(previous)
    this.setPhase('probing-line', full ? '正在探测线路…' : '正在复测线路…')
    const measured = await measureLines(full ? FULL_ROUNDS : QUICK_ROUNDS)
    const decided = decideLine(measured, full ? null : previous)
    if (!decided) throw new AccountApiError('network', '两条线路都连不上，账号相关功能暂不可用。')
    this.data = this.store.patch({ line: decided })
    if (decided.preferred !== previous?.preferred) {
      logDesktop(
        `[account] 线路结论 ${previous?.preferred ?? '（无）'} → ${decided.preferred}，` +
          `实测 ${JSON.stringify(decided.measurements)}`,
      )
    }
  }

  
  private async lookupOrRegister(): Promise<void> {
    const line = this.currentLine()
    const deviceInfo = this.requireDeviceInfo()
    this.setPhase('lookup', '正在检查本机账号…')

    let result: api.LookupResult
    try {
      result = await api.lookup(line, { deviceFp: this.data.deviceFp || undefined, deviceInfo })
    } catch (error) {
      const apiError = toApiError(error)
      
      if (apiError.code !== 'bad-request' && apiError.code !== 'device-unusable') {
        this.store.addPending({ kind: 'lookup', at: Date.now() })
      }
      throw apiError
    }
    this.store.removePending('lookup')

    
    
    const accounts = this.mergeUsers(result.accounts, true)
    const currentId = this.pickCurrentId(result.current_account_id, accounts)
    this.data = this.store.patch({
      deviceFp: result.device_fp || this.data.deviceFp,
      accounts,
      currentId,
    })
    this.publish()

    if (accounts.length === 0) await this.registerCurrentDevice()
  }

  
  private async registerCurrentDevice(): Promise<void> {
    const line = this.currentLine()
    const deviceInfo = this.requireDeviceInfo()
    this.setPhase('register', '正在为本机创建账号…')

    let result: api.RegisterResult
    try {
      result = await api.register(line, { deviceFp: this.data.deviceFp || undefined, deviceInfo })
    } catch (error) {
      const apiError = toApiError(error)
      if (apiError.code !== 'bad-request' && apiError.code !== 'device-unusable') {
        this.store.addPending({ kind: 'register', at: Date.now() })
      }
      throw apiError
    }
    this.store.removePending('register')

    this.data = this.store.patch({
      deviceFp: result.device_fp || this.data.deviceFp,
      accounts: this.mergeUsers([result.user]),
      currentId: result.user.id,
    })
    
    
    if (result.device_secret) this.secrets.set('device_secret', result.device_secret)
    if (result.session_token) {
      this.secrets.set('session_token', result.session_token)
      this.data = this.store.patch({ sessionAccountId: result.user.id })
    }
    logDesktop(
      `[account] 本机账号 ${result.user.account}（created=${result.created}，` +
        `device_secret=${result.device_secret ? '已保存' : '未下发'}）`,
    )
    
    this.syncSession()
    this.publish()
  }

  
  private async pullAccountInfo(): Promise<void> {
    const current = this.currentUser()
    if (!current) return

    const user = await this.fetchCurrentUser(current)
    if (user) this.data = this.store.patch({ accounts: this.mergeUsers([user]) })

    if (this.data.rate === null) {
      try {
        const rate = await api.fetchRate(this.currentLine(), this.authFor(this.currentUser()))
        this.data = this.store.patch({ rate: rate.usdt_to_token })
      } catch (error) {
        
        logDesktop(`[account] 费率暂时取不到：${toApiError(error).message}`)
      }
    }

    const latest = this.currentUser()
    if (latest && !latest.tron_address) {
      try {
        const wallet = await api.fetchWallet(this.currentLine(), this.authFor(latest))
        if (wallet.address) this.updateUser(latest.id, { tron_address: wallet.address })
      } catch (error) {
        
        logDesktop(`[account] 充值地址暂时取不到：${toApiError(error).message}`)
      }
    }
    
    await this.refreshCommission()
    this.publish()
  }

  private async fetchCurrentUser(current: AccountUser): Promise<AccountUser | null> {
    const line = this.currentLine()
    try {
      const { user } = await api.fetchAccount(line, this.authFor(current))
      if (user.id === current.id) return user
      
      logDesktop(
        `[account] 会话与当前账号不一致（会话 ${user.id} / 当前 ${current.id}），丢弃这次结果`,
      )
      this.clearSession()
      if (!this.secrets.has('device_secret')) return null
      const retry = await api.fetchAccount(line, this.authFor(current))
      return retry.user.id === current.id ? retry.user : null
    } catch (error) {
      const apiError = toApiError(error)
      if (apiError.code === 'need-login') this.clearSession()
      if (apiError.code === 'no-auth') return null
      throw apiError
    }
  }

  
  
  
  private scheduleRetry(): void {
    if (this.retryTimer) return
    this.retryTimer = setInterval(() => void this.retryCycle(), RETRY_INTERVAL_MS)
  }

  private async retryCycle(): Promise<void> {
    if (this.checksSkipped || !this.deviceUsable) return
    await this.exclusive(async () => {
      if (this.offline) {
        if (!(await this.checkNetwork())) return
        this.offline = false
        await this.runAccountStages()
        return
      }
      if (this.data.pending.length > 0) await this.flushPending()
    }).catch(() => undefined)
  }

  
  private async flushPending(): Promise<void> {
    if (this.data.pending.some((item) => item.kind === 'invite')) {
      for (const action of this.data.pending.filter((item) => item.kind === 'invite')) {
        if (!action.code) {
          this.store.removePending('invite', action.code)
          continue
        }
        try {
          await this.applyInvite(action.code)
          this.store.removePending('invite', action.code)
        } catch (error) {
          const apiError = toApiError(error)
          logDesktop(`[account] 补填邀请码重试失败：${apiError.message}`)
          
          if (apiError.code === 'conflict' || apiError.code === 'bad-request') {
            this.store.removePending('invite', action.code)
          }
        }
      }
    }
    if (this.data.pending.some((item) => item.kind === 'register' || item.kind === 'lookup')) {
      await this.runAccountStages()
    }
  }

  private async applyInvite(code: string): Promise<void> {
    const current = this.requireUser()
    const result = await api.invite(this.currentLine(), this.authFor(current), code)
    this.data = this.store.patch({
      accounts: this.data.accounts.map((user) =>
        user.id === current.id
          ? {
              ...user,
              invite_bound: true,
              inviter_masked: result.inviter_masked ?? user.inviter_masked ?? null,
            }
          : user,
      ),
    })
    logDesktop(`[account] 邀请码已提交，奖励 ${result.bonus_token} token`)
    
    await this.pullAccountInfo()
  }

  private noteFailure(error: AccountApiError): void {
    logDesktop(`[account] 首启流程中断：${error.code} ${error.message}`)
    if (error.code === 'device-unusable') {
      this.deviceUsable = false
      this.setPhase('device-unusable', error.message)
      return
    }
    if (error.code === 'need-login') this.clearSession()
    if (error.code === 'network' || error.code === 'timeout') {
      this.goOffline(error.message)
      return
    }
    this.setPhase('error', error.message)
  }

  private goOffline(message: string): void {
    this.offline = true
    this.setPhase('offline', message)
    
    
    if (!this.offlineNotified) {
      this.offlineNotified = true
      this.offlinePrompt = true
      this.publish()
    }
  }

  
  
  
  private exclusive<T>(task: () => Promise<T>): Promise<T> {
    const run = this.busy.then(task, task)
    this.busy = run.catch(() => undefined)
    return run
  }

  private async action(task: () => Promise<void>): Promise<AccountActionResult> {
    try {
      await this.exclusive(task)
      return { ok: true, snapshot: this.publish() }
    } catch (error) {
      const apiError = toApiError(error)
      logDesktop(`[account] 操作失败：${apiError.code} ${apiError.message}`)
      return {
        ok: false,
        error: apiError.message,
        manualReset: apiError.manualReset,
        snapshot: this.publish(),
      }
    }
  }

  private setPhase(phase: AccountSnapshot['phase'], message: string): void {
    this.phase = phase
    this.message = message
    this.publish()
  }

  private publish(): AccountSnapshot {
    const snapshot = this.snapshot()
    
    
    const serialized = JSON.stringify(snapshot)
    if (serialized !== this.lastPublished) {
      this.lastPublished = serialized
      this.notify(snapshot)
    }
    return snapshot
  }

  private currentLine(): AccountLine {
    return this.data.line?.preferred ?? 'cn'
  }

  private currentUser(): AccountUser | null {
    const currentId = this.data.currentId
    if (currentId !== null) {
      const found = this.data.accounts.find((user) => user.id === currentId)
      if (found) return found
    }
    return (
      this.data.accounts.find((user) => user.is_primary) ?? this.data.accounts[0] ?? null
    )
  }

  private requireUser(): AccountUser {
    const current = this.currentUser()
    if (!current) throw new AccountApiError('no-account', '本设备还没有账号，请先联网注册。')
    return current
  }

  private requireDeviceInfo(): DeviceInfo {
    const info = this.data.deviceInfo
    if (!info || !isDeviceUsable(info)) {
      throw new AccountApiError('device-unusable', '无法识别本机设备，账号相关功能暂不可用。')
    }
    return info
  }

  





  private authFor(user: AccountUser | null): api.AuthContext {
    const token =
      user && this.data.sessionAccountId === user.id ? this.secrets.get('session_token') : ''
    const deviceSecret = this.secrets.get('device_secret')
    return {
      token: token || undefined,
      deviceSecret: deviceSecret || undefined,
      deviceFp: this.data.deviceFp || undefined,
      account: user?.account,
    }
  }

  
  private deviceAuth(): api.AuthContext {
    const deviceSecret = this.secrets.get('device_secret')
    if (!deviceSecret || !this.data.deviceFp) {
      
      
      throw new AccountApiError(
        'no-auth',
        '本机设备凭据已丢失，改密 / 改名需要的设备签名不可用。' +
          '恢复方式：在「权益 → 密码与安全」里用账号密码登录一次（登录后会自动补发设备密钥），再重试。',
      )
    }
    return { deviceSecret, deviceFp: this.data.deviceFp }
  }

  private clearSession(): void {
    this.secrets.set('session_token', null)
    this.data = this.store.patch({ sessionAccountId: null })
    this.syncSession()
  }

  







  syncSession(): void {
    if (!this.sessionSync) return
    this.sessionSync.push(this.secrets.get('session_token'))
  }

  private async doLogin(account: string | undefined, password: string): Promise<api.LoginResult> {
    
    this.resetPaymentState()
    const result = await api.login(this.currentLine(), {
      deviceInfo: this.requireDeviceInfo(),
      account,
      password,
    })
    this.secrets.set('session_token', result.session_token)
    this.data = this.store.patch({
      accounts: this.mergeUsers([result.user]),
      currentId: result.user.id,
      sessionAccountId: result.user.id,
    })
    
    await this.ensureDeviceKey()
    
    this.syncSession()
    return result
  }

  






  private async ensureDeviceKey(): Promise<void> {
    if (this.secrets.has('device_secret')) return
    if (!this.data.deviceFp) return
    const user = this.currentUser()
    const token =
      user && this.data.sessionAccountId === user.id ? this.secrets.get('session_token') : ''
    if (!token) return
    try {
      
      
      
      
      const result = await api.claimDeviceKey(
        this.currentLine(),
        { token },
        { deviceFp: this.data.deviceFp },
      )
      if (result.device_secret) {
        this.secrets.set('device_secret', result.device_secret)
        logDesktop('[account] 已重新申领设备密钥')
        
        this.publish()
      }
    } catch (error) {
      
      logDesktop(`[account] 设备密钥申领失败：${toApiError(error).message}`)
    }
  }

  


















  private async healDeviceKeyIfMissing(): Promise<void> {
    if (this.secrets.has('device_secret')) return
    try {
      const hadSession = this.secrets.has('session_token')
      if (!hadSession) {
        const user = this.currentUser()
        if (!user) {
          logDesktop('[account] 设备密钥缺失且无账号')
          return
        }
        const deviceInfo = this.requireDeviceInfo()
        if (user.is_primary && !user.has_password) {
          
          let result: api.LoginResult
          try {
            
            result = await api.login(this.currentLine(), {
              deviceInfo,
              mode: 'default',
              emptyPassword: true,
            })
          } catch (firstError) {
            
            logDesktop(
              `[account] 默认登录（mode=default）未成功，改用指定账号重试：${toApiError(firstError).message}`,
            )
            result = await api.login(this.currentLine(), {
              deviceInfo,
              account: user.account,
              mode: 'switch',
              emptyPassword: true,
            })
          }
          this.secrets.set('session_token', result.session_token)
          this.data = this.store.patch({
            accounts: this.mergeUsers([result.user]),
            currentId: result.user.id,
            sessionAccountId: result.user.id,
          })
          logDesktop('[account] 已静默默认登录（空密码），准备补发设备密钥')
        } else {
          
          
          
          try {
            const result = await api.deviceSession(this.currentLine(), { deviceInfo })
            this.secrets.set('session_token', result.session_token)
            this.data = this.store.patch({
              accounts: this.mergeUsers([result.user]),
              currentId: result.user.id,
              sessionAccountId: result.user.id,
            })
            logDesktop('[account] 已用设备指纹换会话（有密码账号），准备补发设备密钥')
          } catch (error) {
            
            logDesktop(`[account] 设备指纹换会话不可用，静默补发未完成：${toApiError(error).message}`)
          }
        }
      }
      await this.ensureDeviceKey()
      
      this.syncSession()
      
      if (!hadSession && this.secrets.has('device_secret')) {
        await this.pullAccountInfo()
      }
    } catch (error) {
      
      logDesktop(`[account] 设备密钥静默补发失败：${toApiError(error).message}`)
    }
  }

  






  private mergeUsers(incoming: AccountUser[], replaceAll = false): AccountUser[] {
    const merged = incoming.map((user) => {
      const cached = this.data.accounts.find((item) => item.id === user.id)
      if (!cached) return user
      return {
        ...cached,
        ...user,
        inviter_masked: user.inviter_masked ?? cached.inviter_masked ?? null,
      }
    })
    if (replaceAll) return merged
    for (const cached of this.data.accounts) {
      if (!merged.some((user) => user.id === cached.id)) merged.push(cached)
    }
    return merged
  }

  private updateUser(id: number, patch: Partial<AccountUser>): void {
    this.data = this.store.patch({
      accounts: this.data.accounts.map((user) => (user.id === id ? { ...user, ...patch } : user)),
    })
  }

  private pickCurrentId(suggested: number | null, accounts: AccountUser[]): number | null {
    
    const existing = this.data.currentId
    if (existing !== null && accounts.some((user) => user.id === existing)) return existing
    if (suggested !== null && accounts.some((user) => user.id === suggested)) return suggested
    return accounts.find((user) => user.is_primary)?.id ?? accounts[0]?.id ?? null
  }
}
