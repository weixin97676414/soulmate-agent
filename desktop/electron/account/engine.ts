/**
 * 账号引擎：静默首启（文档 §6.1 的 S0–S8）+ 完整性补偿（§6.4）+ 用户动作 + 快照广播。
 *
 * ## 为什么"静默"
 *
 * 用户要的是"双击图标就开始用"：账号是**后台准备**的东西，不该在启动时挡一屏
 * 要他点"下一步"。所以整条 S0–S8 都在后台跑，权益页需要时才读快照。
 * 唯一的例外是断网 —— 那种情况下账号功能确实不可用，必须让用户知道（§6.1 S2）。
 *
 * ## 为什么所有入口都串行
 *
 * 用户动作（切账号 / 改密）与后台流程（首启、补偿、60 秒重试）会撞在一起：
 * 用户在首启还没跑完时就点"刷新"，两边各跑一遍 lookup + register，
 * 后果是**同一个设备建出两个账号**（真花钱）。所以引擎内部只有一条队列，
 * 后台流程与用户动作都排队走它。
 */
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

/** 离线后的静默重试间隔（文档 §6.1 S2） */
const RETRY_INTERVAL_MS = 60_000
/** 联网检测的单次探测超时（文档 §6.1 S2：1.5s） */
const NETWORK_PROBE_TIMEOUT_MS = 1_500
/** 账号名允许的形态（文档 §5.10） */
const ACCOUNT_NAME = /^[A-Za-z0-9_]{3,32}$/
const MIN_PASSWORD = 6
/** 微信查单轮询间隔（文档 §3.2：2~3 秒一次，最多 5 分钟） */
const WX_POLL_MS = 2_500
const WX_MAX_YUAN = 50_000
/** PayPal 查单轮询间隔（文档 §3：每 3 秒一次） */
const PAYPAL_POLL_MS = 3_000
/**
 * 服务端没下发 `expires_in` 时的结账窗口兜底（秒）。
 *
 * 有效期**以服务端为准**：`ct` 是服务端签发并绑了时间的一次性凭证，客户端自己
 * 写死一个数字就意味着"服务端改了有效期，客户端还在按旧数倒计时"—— 倒计时走到 0
 * 而链接其实还有效（或者反过来）都会让用户误判。只在字段缺失时才退回 30 分钟。
 */
const PAYPAL_DEFAULT_EXPIRES_SECONDS = 1_800
/**
 * 服务端没下发 min / max 时的安全默认值。
 *
 * 宁可默认保守（1–100），也不要给一个"能下巨单"的上限：限额是运营随时会调的
 * 风控参数，配置缺失时按最保守的口径走，最坏结果只是用户抱怨限额小，而不是
 * 一笔远超预期的订单被放出去。
 */
const PAYPAL_DEFAULT_MIN = 1
const PAYPAL_DEFAULT_MAX = 100

export type SnapshotListener = (snapshot: AccountSnapshot) => void

/**
 * 结账窗口由主进程（main.ts）持有 —— `BrowserWindow` 是"壳"的一部分，
 * 不属于账号引擎。引擎只决定"什么时候开、什么时候关"，通过这个回调交给壳。
 */
export interface PaypalCheckoutHost {
  open(url: string): void
  close(): void
}

/**
 * 会话凭证的**核心代发**同步口（心鉴学报告接口的凭证由核心代发）。
 *
 * 引擎这里只有 token、没有核心的 baseUrl + X-Local-Token（那些在 main.ts 的
 * BackendManager 里），所以把"推给核心"这个动作反向交给壳：引擎在凭证变化时调
 * `push`，壳负责落到 `PUT /v1/client/session`。空串 = 已登出（核心要清掉）。
 *
 * ⚠️ 凭证**只走这条通道**，绝不进快照 / IPC 到渲染层（见 secure.ts 的说明）。
 */
export interface SessionSync {
  push(token: string): void
}

function toApiError(error: unknown): AccountApiError {
  if (error instanceof AccountApiError) return error
  return new AccountApiError('network', error instanceof Error ? error.message : String(error))
}

/** 后端 status 字符串归一化。认不出来的当 PENDING：继续轮询比误判"已结束"安全。 */
function normalizePaypalStatus(raw: string): PayPalOrderStatus {
  const value = raw.trim().toLowerCase()
  if (value === 'paid' || value === 'success' || value === 'completed') return 'PAID'
  if (value === 'expired') return 'EXPIRED'
  if (value === 'cancelled' || value === 'canceled') return 'CANCELLED'
  if (value === 'failed' || value === 'fail') return 'FAILED'
  return 'PENDING'
}

/**
 * 结账窗口有效期（秒）：**以服务端下发的 `expires_in` 为准**，缺失才退回 30 分钟。
 *
 * `Number(undefined)` 是 NaN、`Number('')` 是 0、`Number(null)` 是 0 —— 三种都必须
 * 走到兜底，否则倒计时会立刻算成"已过期"，用户刚点开窗口就被判定超时。
 */
function paypalExpiresSeconds(raw: unknown): number {
  const value = Number(raw)
  if (!Number.isFinite(value) || value <= 0) return PAYPAL_DEFAULT_EXPIRES_SECONDS
  return Math.round(value)
}

/**
 * 日志里只留 `ct` 的前 8 位。
 *
 * `ct` 是"拿着它就能查这一单状态"的一次性凭证，完整值没有进日志的必要 ——
 * 与"头像 / 图片的 base64 绝不进日志"同一条规矩：能撤销的凭证也不该被抄到磁盘上。
 */
function shortCt(ct: string): string {
  return ct ? `ct=${ct.slice(0, 8)}…` : 'ct=（空）'
}

/**
 * PayPal 错误码对照（《方案 B·最终版》§3）。
 *
 * **裁决权放在主进程**：同一个 409 在不同接口下含义不同，这类判断一旦散落到各个
 * 组件里，改一处就会漏掉另一处；界面只拿 `tone` + 文案照着画，不自己猜。
 *
 * ⚠️ 服务端原话永远跟着走：映射文案后面附上 `error.message`，谁都不吞谁的 ——
 * 用户才知道该找谁、是不是自己的问题。
 */
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
      // ⚠️ 400 一律**以服务端原话为准**，客户端不翻译、不总结，更不许假称自己做了什么。
      // 0.1.43~0.1.53 这里写死成「数量需在 1–100 之间」并附带一句"已经替你调整好了" ——
      // 而 400 的真实原因远不止数量（ct 过期、参数不符、订单不存在…）。用户实测过代价：
      // 数量填 10（本来就合法，客户端也**没有**改过它）却被告知已替他调整过，
      // 同一条提示里还挂着"支付链接已失效"，两个说法互相打脸，谁看了都不知道该信哪句。
      // （旧文案里那四个字是个"不许出现在本文件"的哨兵：结构闸按原样源码比对，写回注释里也会红。）
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
  /** 用户选了"跳过检测"：本次运行不再自动重试 */
  private checksSkipped = false
  private balanceIncreasedAt: number | null = null
  private retryTimer: NodeJS.Timeout | null = null
  /** 单条队列：后台流程与用户动作共用（见模块说明） */
  private busy: Promise<unknown> = Promise.resolve()
  private lastPublished = ''
  /** 佣金余额 + 提现记录（运行态，不进 account.json；切账号 / 切线路时清掉） */
  private commission: AccountCommission | null = null
  /**
   * 上次拉佣金失败的原因（空串 = 这次拉成功过）。
   *
   * 它进快照、推到界面上 —— 佣金取不到时界面必须**有话说**（"为什么没有数字"），
   * 而不是留一张空卡片让用户反复点刷新。见 `pullCommission` 的说明。
   */
  private commissionError = ''
  /** 当前微信订单（大陆线路）。只有 CREATING/NOTPAY 会被持续轮询 */
  private wxOrder: WxOrderState | null = null
  private wxExpiresAt = 0
  private wxTimer: NodeJS.Timeout | null = null
  /** PayPal 渠道配置（首尔线路；切线路 / 切账号时清掉，见 resetPaymentState） */
  private paypalConfig: PayPalConfig | null = null
  /** 当前 PayPal 订单（运行态，不进 account.json） */
  private paypalOrder: PayPalOrderState | null = null
  /** PayPal 结账窗口的过期时刻（毫秒） */
  private paypalExpiresAt = 0
  private paypalTimer: NodeJS.Timeout | null = null
  /** 最近一次 PayPal 提示（进快照：轮询结果也必须让界面有回音） */
  private paypalNotice: PayPalNotice | null = null

  constructor(
    private readonly notify: SnapshotListener,
    /** 结账窗口的开/关由壳（main.ts）执行，引擎只发号施令 */
    private readonly paypalHost?: PaypalCheckoutHost,
    /** 会话凭证推给核心的通道（见 SessionSync 的说明） */
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
        // USDT 到账会让邀请人产生佣金，顺手刷新佣金展示（失败只记日志，不打断）
        void this.refreshCommission()
      },
      publish: () => this.publish(),
    })
  }

  // ------------------------------------------------------------------ //
  // 生命周期
  // ------------------------------------------------------------------ //
  /** 启动静默首启。**故意不返回 Promise**：调用方不该 await 它，界面要立刻可用。 */
  start(): void {
    this.publish()
    // 测试逃生门：验收脚本用它把"主应用"的账号网络活动整个关掉 —— 否则验证
    // 过程中那个没指到本地 mock 的实例会打到生产后端、给测试机建一个真账号。
    // 真机联调与正常使用**永远不设**这个变量。
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
    // 退出时把结账窗口一起收掉：留着它会挂着一个没人再轮询的 PayPal 页面
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
      // 失败原因一起下发：界面据此显示"返佣没取到：<原因>"（空串 = 没出过错）
      commissionError: this.commissionError,
      wxOrder: this.wxOrder,
      paypalConfig: this.paypalConfig,
      paypalOrder: this.paypalOrder,
      paypalNotice: this.paypalNotice,
    }
  }

  /** 完整性补偿（文档 §6.4），同时也是"重试"按钮与进权益页时的入口。 */
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

  // ------------------------------------------------------------------ //
  // 用户动作
  // ------------------------------------------------------------------ //
  async setAccountLine(line: AccountLine): Promise<AccountSnapshot> {
    const measurements = this.data.line?.measurements ?? {}
    this.data = this.store.patch({
      line: { preferred: line, measurements, updatedAt: Date.now(), manual: true },
    })
    // 微信订单是大陆专属的，切到另一条线它就没意义了（文档 §1：按线路只显示对应一套）
    this.resetPaymentState()
    logDesktop(`[account] 用户手动切换线路到 ${line}`)
    return this.publish()
  }

  /** 「重新测速」：无视 24 小时有效期，强制重跑一次完整探测。 */
  async reprobeLines(): Promise<AccountSnapshot> {
    await this.exclusive(async () => {
      if (!this.deviceUsable) return
      await this.probeLinesIfNeeded(true)
    }).catch(() => undefined)
    return this.snapshot()
  }

  /** 登录**其他**账号（不在本机列表里）：必须账号 + 密码。 */
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
      // 这两条预检只是**省一次往返**，真正的规则在后端（文档 §5.5）：
      // 空密码只对"本机自动创建的那个账号"有效
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
      // 改密/改名必须设备签名：动手前先静默补一次密钥（有密钥时零开销直接返回）
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
      // 改密/改名必须设备签名：动手前先静默补一次密钥（有密钥时零开销直接返回）
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
        // 离线时**记下来**而不是让用户白输一次（文档 §6.4：联网后自动重试）
        this.store.addPending({ kind: 'invite', code: trimmed, at: Date.now() })
        throw new AccountApiError(
          'network',
          '当前网络不可用，已记下这个邀请码，联网后会自动提交。',
        )
      }
      await this.applyInvite(trimmed)
    })
  }

  /**
   * 兑换码充值 Token（文档《兑换码充值Token-前端接入说明》）。
   *
   * 与其它 action 不同，它要把**后端那句成功文案**（"充值成功，获得 60 Token"）
   * 原样带给界面，所以返回自己的结果类型，而不是共用的 `AccountActionResult`。
   *
   * **一次都不重试**：码是一次性核销的；"已被使用 / 不存在 / 已禁用"这些原因
   * 必须原样给用户看 —— 他要知道下一步做什么。
   */
  async redeem(code: string): Promise<RedeemOutcome> {
    const trimmed = code.trim()
    if (!trimmed) {
      return { ok: false, message: '', error: '请填写兑换码。', snapshot: this.publish() }
    }
    try {
      const message = await this.exclusive(async () => {
        const current = this.requireUser()
        const result = await api.redeemCode(this.currentLine(), this.authFor(current), trimmed)
        // 后端把新余额一并返回了（文档 §2.3）：直接用它刷新展示，省一次往返
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

  // ------------------------------------------------------------------ //
  // 支付 / 返佣 / 提现（《微信支付接入文档》v1.0）
  // ------------------------------------------------------------------ //
  /**
   * 拉一次佣金余额与提现记录（界面上的「刷新」按钮走这里）。
   *
   * **失败会如实返回 `ok:false` + 原因**：界面得能告诉用户"为什么还是没数字"。
   * 「顺手刷一下」的内部流程请用 `refreshCommission()`（它不抛）。
   */
  async getCommission(): Promise<AccountActionResult> {
    return this.action(async () => {
      // 点刷新也是一次自愈机会：首启那次 heal 可能因网络抖动失败过，
      // 这里静默再试一次（有密钥时它直接返回，零开销），失败不挡拉取
      await this.healDeviceKeyIfMissing()
      await this.pullCommission()
    })
  }

  /** 微信扫码下单（大陆）。成功后主进程开始按 2.5s 轮询查单。 */
  async createWxRecharge(amountYuan: number): Promise<AccountActionResult> {
    return this.action(async () => {
      if (!Number.isInteger(amountYuan) || amountYuan < 1 || amountYuan > WX_MAX_YUAN) {
        throw new AccountApiError('bad-request', `充值金额必须是 1~${WX_MAX_YUAN} 的整数（元）。`)
      }
      if (this.currentLine() !== 'cn') {
        throw new AccountApiError('forbidden', '微信充值仅在大陆线路开放，请切换到大陆线路。')
      }
      // 已有同一金额的未完成订单：不重复下单，直接沿用（文档 §3.1）
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

  /** 取消当前微信订单（用户点「重新生成」或「完成」时）。 */
  async cancelWxRecharge(): Promise<AccountSnapshot> {
    this.stopWxPolling()
    this.wxOrder = null
    this.wxExpiresAt = 0
    return this.publish()
  }

  // ------------------------------------------------------------------ //
  // PayPal 充值（首尔线路专有）
  // ------------------------------------------------------------------ //

  /**
   * 线路闸：PayPal 只在首尔线可用。
   *
   * 闸口放在**引擎**而不是界面：界面上的显隐只是"不给你看"，绕过界面（旧版本客户端、
   * 手工 IPC）仍要能挡住，所以真正的裁决必须在这里。
   */
  private paypalLineGate(): PayPalNotice | null {
    if (this.currentLine() === 'seoul') return null
    return { tone: 'danger', message: 'PayPal 充值仅在首尔线路开放，请先切换到首尔线路。' }
  }

  /**
   * 拉 PayPal 渠道配置（单价 / 数量上下限 / client_id / mode）。
   *
   * **价格与限额一律以服务端下发为准**，这里只在字段缺失时补安全默认值：写死价格意味着
   * 后端调价后界面还按旧价试算，用户按旧价付钱却拿到对不上的 Token —— 这类账目偏差
   * 无法自愈，只能靠"不写死"从源头避免。
   */
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
      // ⚠️ 字段映射（产品以文档为准）：服务端给的是 unit_tokens /
      // max_quantity / unit_usd，内部口径是 unit_price / max / unit_usd ——
      // 映射只收在这一个地方，服务端与网页线的口径都不用动。
      // 旧字段名（unit_price / max）保留作兼容：后端版本不同，少给新键时退回旧键。
      // `Number(undefined)` 是 NaN，必须显式判掉，否则数值会变成 NaN 一路传下去。
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

  /**
   * 发起 PayPal 结账：建会话（拿一次性 `ct` + 结账地址）→ 开独立结账窗口 → 每 3 秒查单。
   *
   * ⚠️ 客户端只调 `POST /paypal/session`（方案 B）：`ct` 是服务端签发的一次性凭证，
   * 结账页与轮询都靠它。`checkout/create` 是**结账页内部**接口，客户端调它必被拒 ——
   * 服务端回的原话就是「支付链接已失效，请重新发起」，这正是 0.1.53 收款走不通的根因。
   *
   * 数量在**下单前**按服务端下发的 min–max 夹紧：配置可能还没拉到（用户手快），
   * 与其发一个注定 400 的请求，不如本地先夹到合法区间，并把实际用的份数记进订单。
   * ⚠️ 夹紧是"本地自己收敛"，与提示文案无关 —— 不许再对外宣称"已经替你调整好了"。
   *
   * ⚠️ 凭证（session_token）与 `ct` 都只留在主进程：`checkout_url` 是后端签发的临时地址，
   * 不含登录态，渲染层拿到的也永远只是结果快照。
   */
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
      // 两种命名都认：后端换过字段名，客户端同时兼容才不至于新旧版本互相卡死
      const url = result.checkout_url || result.approve_url || ''
      const ct = String(result.ct ?? '').trim()
      if (!url || !ct) {
        // 少了任何一个，这一单都无法"开窗 + 后续查单"，与其开一个查不到结果的窗口，不如当场说清楚
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

  /** 取消当前 PayPal 结账（关窗 + 停轮询）。语义与 `cancelWxRecharge` 保持一致。 */
  async cancelPaypalCheckout(): Promise<AccountSnapshot> {
    this.stopPaypalPolling()
    this.paypalHost?.close()
    this.paypalOrder = null
    this.paypalExpiresAt = 0
    this.paypalNotice = null
    return this.publish()
  }

  /**
   * 清掉当前 PayPal 提示（用户改了数量、或重新发起下单之前）。
   *
   * 提示记的是"**上一次动作**的结论"，与此刻的输入无关：用户把数量改回合法区间后，
   * 上一条红字还挂在卡片上，看起来就像"改完还是错的" —— 这是实测反馈第 7 条。
   * 所以数量一变就由界面调它把旧结论擦掉（本次的结论由下一次动作重新写）。
   */
  dismissPaypalNotice(): AccountSnapshot {
    this.paypalNotice = null
    return this.publish()
  }

  /**
   * 结账窗口被用户关掉时，由壳（main.ts）回调告知。
   *
   * 已经结束的订单（到账 / 过期 / 取消）一律不动：那些提示是引擎自己写好的，
   * 在这里再处理一次会把「已到账」覆盖成「已取消」，让用户以为钱白付了。
   */
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

  /** 每个心跳：先判服务端给的有效期是否到点，再查一次单。 */
  private async paypalTick(): Promise<void> {
    const order = this.paypalOrder
    if (!order) return
    if (Date.now() >= this.paypalExpiresAt) {
      this.stopPaypalPolling()
      this.paypalHost?.close()
      this.paypalOrder = { ...order, status: 'EXPIRED', countdown_seconds: 0 }
      // 不写具体分钟数：有效期由服务端下发，写死一个数字就会出现"提示说 30 分钟、
      // 实际 15 分钟就断"这种对不上的话术
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

  /**
   * 查单。
   *
   * 502 表示支付网关还在同步 —— **继续轮询**（文档 §3 明确要求），不要停表：用户这时
   * 往往刚付完，停表会让他以为支付失败而重复付款。
   */
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
          // `already` = 这笔订单此前已入账过（用户重复点了付款 / 上一轮没刷到），直接刷余额即可
          message: result.already ? '这笔充值已到账，余额已刷新。' : '支付成功，Token 已到账。',
        }
        this.balanceIncreasedAt = Date.now()
        logDesktop(
          `[account] PayPal 本次充值已到账（already=${result.already}，` +
            `+${result.token_amount ?? '?'} Token，${shortCt(order.ct)}）`,
        )
        try {
          await this.pullAccountInfo() // 刷新余额
          await this.refreshCommission() // 充值会带来邀请人的佣金，顺手刷
        } catch (error) {
          // 到账事实已经确定了，刷新失败不能反过来把它盖成"失败"
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
      if (apiError.status === 502) return // 网关同步中，下一轮继续查
      this.stopPaypalPolling()
      this.paypalHost?.close()
      this.paypalNotice = paypalErrorNotice(apiError)
      if (apiError.status === 404) {
        // 订单后端已查不到，本地再等也不会有结果，直接按失效处理，让用户重新发起
        this.paypalOrder = { ...order, status: 'EXPIRED', countdown_seconds: 0 }
      }
      this.publish()
    }
  }

  /**
   * 人民币提现（大陆，3% 手续费）。
   *
   * 收款口径（清单 §5.2）：支付宝号 或 银行卡号，有一个即可。这里负责把两个字符串
   * 收敛成后端要的 `method` / `payee`：填了哪个用哪个（都填了优先支付宝），
   * 都没填时回看账号里已存过哪个（`payee_ready`）；仍都没有才报错。
   */
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

  /** USDT 提现（国际，固定 1 USDT/次手续费）。 */
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

  /**
   * 拉佣金。**失败会抛出**，并把原因记进 `commissionError`（快照会带着它推给界面）。
   *
   * ⚠️ 这里原先把异常吞掉、只打一行日志，后果是 `action()` **永远**返回 `ok:true` ——
   * 界面上手动刷新转个圈就没下文，用户只知道"点了没反应"（实测反馈缺陷）。
   * 佣金确实是展示性数据、不该打断主流程，但**更不能假装成功**：让调用方自己决定
   * 是"记日志继续"（下面那个包装）还是"如实报给用户"（界面点刷新）。
   */
  private async pullCommission(): Promise<void> {
    const current = this.currentUser()
    if (!current) return
    try {
      this.commission = await api.fetchCommission(this.currentLine(), this.authFor(current))
      this.commissionError = ''
    } catch (error) {
      this.commissionError = toApiError(error).message
      logDesktop(`[account] 佣金取不到：${this.commissionError}`)
      // 先把失败原因推下去（否则界面拿不到它），再把异常交给调用方
      this.publish()
      throw error
    }
    this.publish()
  }

  /** 「顺手刷一下」：轮询、提现后、首启拉信息用。失败只记日志，不打断调用方。 */
  private async refreshCommission(): Promise<void> {
    try {
      await this.pullCommission()
    } catch {
      // 原因已经记进 commissionError 并推给界面了，这里只是不往上抛
    }
  }

  /** 清掉与账号/线路绑定的支付态（切账号、切线路时调用）。 */
  private resetPaymentState(): void {
    this.stopWxPolling()
    this.wxOrder = null
    this.wxExpiresAt = 0
    // PayPal 订单与配置同样绑定线路/账号：切走之后留着它，用户会以为那笔还在进行中
    this.stopPaypalPolling()
    this.paypalHost?.close()
    this.paypalOrder = null
    this.paypalExpiresAt = 0
    this.paypalConfig = null
    this.paypalNotice = null
    this.commission = null
    // 失败原因也要清：换了账号/线路还留着上一个账号的报错，会让人以为新账号也取不到
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

  /** 每个轮询心跳：先推进倒计时，再查一次单。 */
  private async wxTick(): Promise<void> {
    if (!this.wxOrder) return
    // 倒计时归零但后端还没回 CLOSED 时，本地先按过期处理（宁可早一步提示，别让
    // 用户对着一张过期码干等 —— 码过期后再扫只会失败）
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
        await this.pullAccountInfo() // 刷新余额
        await this.refreshCommission() // 刷新佣金
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
      // 订单不存在（404）＝已过期，当作 CLOSED 停下，别再空转
      if (apiError.code === 'no-account') {
        this.stopWxPolling()
        this.wxOrder = { ...order, status: 'CLOSED', countdown_seconds: 0 }
        this.publish()
      }
    }
  }

  // ------------------------------------------------------------------ //
  // 首启状态机
  // ------------------------------------------------------------------ //
  private async boot(): Promise<void> {
    // S1：先把**本地缓存**播出去。权益页这时就能显示"上次是谁、余额多少"，
    //     而不是等几个网络往返之后才有内容（离线时更是只有它）
    this.publish()

    // S0：设备指纹。每次启动都重采 —— 这正是"换目录/重装后仍能认出旧账号"的依据
    const info = await collectDeviceInfo(true)
    this.data = this.store.patch({ deviceInfo: info })
    if (!isDeviceUsable(info)) {
      this.deviceUsable = false
      this.setPhase('device-unusable', '无法识别本机设备，账号相关功能暂不可用。')
      logDesktop('[account] 设备主判据全空，账号功能不可用（不再重试）')
      return
    }
    this.deviceUsable = true

    // S2：联网检测
    this.setPhase('checking-network', '正在检查网络…')
    if (!(await this.checkNetwork())) {
      this.goOffline('当前网络不可用，账号相关功能暂不可用。')
      return
    }
    this.offline = false

    // S3–S7。首启**每次**都做完整双链测速（忽略上次手动切换），选网速最快的（见 probeLinesIfNeeded）
    await this.runAccountStages(true)
    await this.flushPending()
    // 静默补回设备密钥：重装后首启走到这里时，secret 与 session 可能都已丢（DPAPI 解不开），
    // 靠这一次自愈把密钥补回来（见 healDeviceKeyIfMissing），全程不弹框
    await this.healDeviceKeyIfMissing()
  }

  /** 网卡 → DNS/握手。任一侧能探通就算"有网"。 */
  private async checkNetwork(): Promise<boolean> {
    // family 在 Node 的不同版本里出现过 'IPv4' 与 4 两种形态，`String()` 一把抓完
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
        // 换另一条线再试
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

  /**
   * S3：线路探测。结论超过 24 小时就重跑完整探测，否则只做 2 轮复测。
   *
   * ⚠️ 完整测速（`force` = 每次启动 / 手动「重新测速」）时**忽略上次手动切换**：
   * `decideLine` 传 null，走"无旧结论"分支直接挑网速最快的（两线相当按语言属地），
   * 同时 manual 归 false —— 重启后不再沿用上次手动选的那条（产品要求）。
   */
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

  /** S4 / S5：查号，没有账号才注册。 */
  private async lookupOrRegister(): Promise<void> {
    const line = this.currentLine()
    const deviceInfo = this.requireDeviceInfo()
    this.setPhase('lookup', '正在检查本机账号…')

    let result: api.LookupResult
    try {
      result = await api.lookup(line, { deviceFp: this.data.deviceFp || undefined, deviceInfo })
    } catch (error) {
      const apiError = toApiError(error)
      // 参数类错误（400）重试没有意义，其余的联网后自动补
      if (apiError.code !== 'bad-request' && apiError.code !== 'device-unusable') {
        this.store.addPending({ kind: 'lookup', at: Date.now() })
      }
      throw apiError
    }
    this.store.removePending('lookup')

    // lookup 回的是"本设备绑定过的全部账号"，是**权威且完整**的一份，所以直接替换；
    // 别的接口（/account、/login）只回一个账号，那些走合并
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

  /** S5：注册（只有本机没有账号时才走到这里）。 */
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
    // ⚠️ device_secret 只在**首次创建**时出现一次（文档 §4.2），拿到就立刻进加密存储；
    // 丢了只能走找回流程，而且换不回来
    if (result.device_secret) this.secrets.set('device_secret', result.device_secret)
    if (result.session_token) {
      this.secrets.set('session_token', result.session_token)
      this.data = this.store.patch({ sessionAccountId: result.user.id })
    }
    logDesktop(
      `[account] 本机账号 ${result.user.account}（created=${result.created}，` +
        `device_secret=${result.device_secret ? '已保存' : '未下发'}）`,
    )
    // 注册刚拿到的新会话，也要同步给核心（心鉴学报告代发要用它）
    this.syncSession()
    this.publish()
  }

  /** S6 + S7：账号信息、费率、充值地址的补齐。 */
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
        // 费率取不到只是少一行展示，不该中断首启（建议值也能用）
        logDesktop(`[account] 费率暂时取不到：${toApiError(error).message}`)
      }
    }

    const latest = this.currentUser()
    if (latest && !latest.tron_address) {
      try {
        const wallet = await api.fetchWallet(this.currentLine(), this.authFor(latest))
        if (wallet.address) this.updateUser(latest.id, { tron_address: wallet.address })
      } catch (error) {
        // 地址为空**不是错误**（文档 §5.4），后端也会自动补，重试即可
        logDesktop(`[account] 充值地址暂时取不到：${toApiError(error).message}`)
      }
    }
    // 佣金是展示性数据，取不到只记日志，不阻断首启
    await this.refreshCommission()
    this.publish()
  }

  private async fetchCurrentUser(current: AccountUser): Promise<AccountUser | null> {
    const line = this.currentLine()
    try {
      const { user } = await api.fetchAccount(line, this.authFor(current))
      if (user.id === current.id) return user
      // 会话指向另一个账号：绝不拿它去覆盖当前账号的余额（见 store.ts 的说明）
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

  // ------------------------------------------------------------------ //
  // 重试与补偿
  // ------------------------------------------------------------------ //
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

  /** 处理待重试队列（只处理**幂等**的动作，见 store.ts 的说明）。 */
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
          // 已经绑过 / 码本身无效 —— 都不是"再试一次就能好"的情况，别再排队
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
    // 奖励会改变余额，直接以服务端为准重拉一次
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
    // 断网弹窗**一个会话只弹一次**：否则每 60 秒静默重试失败一次就弹一次，
    // 用户会疯（"跳过检测"也只是把重试关掉，界面照旧可用）
    if (!this.offlineNotified) {
      this.offlineNotified = true
      this.offlinePrompt = true
      this.publish()
    }
  }

  // ------------------------------------------------------------------ //
  // 小工具
  // ------------------------------------------------------------------ //
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
    // 只在**内容真的变了**时推：盯单期间每秒都会 publish 一次，
    // 不去重的话渲染层每秒都要重画一遍整页
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

  /**
   * 请求凭据。
   *
   * ⚠️ 会话 token **只在它确实属于这个账号时**才带上：切到别的账号后旧会话还在手上，
   * 带上它会读到**另一个账号**的余额与充值地址（见 store.ts 的 `sessionAccountId`）。
   */
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

  /** 改密 / 改名：后端要求**必须**设备签名。 */
  private deviceAuth(): api.AuthContext {
    const deviceSecret = this.secrets.get('device_secret')
    if (!deviceSecret || !this.data.deviceFp) {
      // 与 api.ts 那条同因同解：device_secret 丢了就换不回来（只在注册响应里出现过一次），
      // 重启没用；可行的是用账号 + 密码登录一次，登录后会自动补发设备密钥（见 SecurityCard）。
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

  /**
   * 把当前会话凭证推给核心（登出 / 未登录时推空串）。见 ``SessionSync`` 的说明。
   *
   * ⚠️ **每次凭证变化都调一次**：核心内存里的凭证是"上次推的那份"，漏推一次
   * 就会拿着一个过期 token 去打报告接口（表现为心鉴学报告稳定 401），
   * 而这类"稳定 401"最容易被误判成"没登录"。空串同样要推 —— 登出后不推，
   * 核心会继续拿旧 token 去请求，把一个已经登出的账号身份留在报告链路里。
   */
  syncSession(): void {
    if (!this.sessionSync) return
    this.sessionSync.push(this.secrets.get('session_token'))
  }

  private async doLogin(account: string | undefined, password: string): Promise<api.LoginResult> {
    // 换成另一个账号后，旧账号的微信订单与佣金展示都不该再挂在界面上
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
    // 登录成功顺手修设备密钥：仅当本地确实没有时（见 ensureDeviceKey 的注释）
    await this.ensureDeviceKey()
    // 登录拿到新会话 → 同步给核心（放在 ensureDeviceKey 之后：它内部可能再换一次会话）
    this.syncSession()
    return result
  }

  /**
   * 本地没有 device_secret 时，用会话向后端重新申领一把。
   *
   * ⚠️ **只在缺失时调用**：申领是"轮换"语义 —— 每申领一次旧签名立即失效，
   * 无脑每次登录都调，可能打断正在飞行中的设备签名请求。所以这里先判
   * `secrets.has('device_secret')`，有了就直接返回。
   */
  private async ensureDeviceKey(): Promise<void> {
    if (this.secrets.has('device_secret')) return
    if (!this.data.deviceFp) return
    const user = this.currentUser()
    const token =
      user && this.data.sessionAccountId === user.id ? this.secrets.get('session_token') : ''
    if (!token) return
    try {
      // ⚠️ `claimDeviceKey(line, auth, params)`：`device_fp` 必须放**第三个参数**才会进
      // 请求体；放进 auth 只会被当成"设备签名用的指纹"（而这条接口 signed:false 根本
      // 不用它），结果 body 是空的 → 后端 400「缺少设备指纹」。这就是设置密码一直
      // "没有凭证"的真凶（返佣走 token 所以没事，设置密码走设备签名所以露馅）。
      const result = await api.claimDeviceKey(
        this.currentLine(),
        { token },
        { deviceFp: this.data.deviceFp },
      )
      if (result.device_secret) {
        this.secrets.set('device_secret', result.device_secret)
        logDesktop('[account] 已重新申领设备密钥')
        // 密钥状态变了（hasDeviceSecret false→true），推一次快照，让权益页的恢复提示消失
        this.publish()
      }
    } catch (error) {
      // 补不上不该阻断登录本身
      logDesktop(`[account] 设备密钥申领失败：${toApiError(error).message}`)
    }
  }

  /**
   * 静默补回设备密钥（自愈，不弹框、不打扰）。
   *
   * 触发场景：重装系统 / 换 Windows 用户后，DPAPI 解不开 `account-secrets.bin`，
   * 于是 `device_secret` 与 `session_token` **一起丢**；但明文账号缓存（`account.json`）
   * 还在，首启 `lookup` 认出了账号、手上却没有会话 —— 返佣/钱包/改密这些要设备签名
   * 的接口全部失败。
   *
   * ⚠️ 0.1.37 的教训：这里**不能**复用 `doLogin` —— 它硬编码 `mode:'switch'` 且空串
   * password 会被过滤成"不带 password 字段"，后端按切换账号的严格规则拒掉，静默登录
   * 一次都没成功过（界面上"已自动恢复"的小字一直不消失就是这个原因）。
   * 正确姿势是文档 §5.5 的**默认登录**：`mode:'default'` + `account` 省略（后端自己找
   * 本设备默认账号）+ 显式空密码 —— 本设备自动创建的账号可以空密码直接进入。
   *
   * 补发成功后还要**把首启时因缺凭据失败的那些展示数据重拉一遍**（返佣/余额/地址）：
   * 首启的 `pullAccountInfo` 跑在 heal 之前，那时 secret 还缺、返佣已记下一句
   * "没取到" —— 不重拉的话，就算密钥补回来了，界面上挂着的还是旧错误，
   * 用户就得手动点刷新（那就不是"不影响用户使用"了）。
   */
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
          // 无密码主账号：空密码默认登录（§5.5 空密码只对本设备自动创建的账号有效）
          let result: api.LoginResult
          try {
            // 最字面的姿势：default 模式 + account 省略 + 显式空密码（§5.5）
            result = await api.login(this.currentLine(), {
              deviceInfo,
              mode: 'default',
              emptyPassword: true,
            })
          } catch (firstError) {
            // 个别后端版本对 default 的实现不同：退回 switch + 指定账号 + 空密码再试一次
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
          // 有密码账号：用设备指纹换会话（后端新口子 /account/device-session，不需要密码）。
          // 密码在本应用里只用于官网导入/导出搭子，本机登录本就该凭设备指纹 ——
          // 所以设没设密码，本机都应该能静默拿到会话、补回密钥。
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
            // 后端口子还没上线（404）或设备未绑定：只能放弃，记日志
            logDesktop(`[account] 设备指纹换会话不可用，静默补发未完成：${toApiError(error).message}`)
          }
        }
      }
      await this.ensureDeviceKey()
      // 静默登录 / 设备指纹换会话可能刚把 session_token 换新 → 同步给核心
      this.syncSession()
      // 会话是刚登录拿到的（或密钥刚补回）→ 把首启时失败的展示数据重拉一遍
      if (!hadSession && this.secrets.has('device_secret')) {
        await this.pullAccountInfo()
      }
    } catch (error) {
      // 自愈失败只记日志：不该打断首启，也不该拿个弹框烦用户
      logDesktop(`[account] 设备密钥静默补发失败：${toApiError(error).message}`)
    }
  }

  /**
   * 合并服务端下发的账号信息。
   *
   * `replaceAll` 只在"这份数据是完整列表"时用（`/account/lookup`）：它会丢掉
   * 本地多出来的那些账号。其余接口只回一个账号，此时必须**保留**本地其余的 ——
   * 一次局部刷新不该让列表里别的账号凭空消失。
   */
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
    // 本地"上次使用"优先于后端建议（文档 §5.3 允许客户端覆盖）
    const existing = this.data.currentId
    if (existing !== null && accounts.some((user) => user.id === existing)) return existing
    if (suggested !== null && accounts.some((user) => user.id === suggested)) return suggested
    return accounts.find((user) => user.is_primary)?.id ?? accounts[0]?.id ?? null
  }
}
