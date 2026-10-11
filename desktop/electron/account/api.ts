/**
 * 账号后端接口封装（文档 §5，共 12 个）。
 *
 * ## 为什么所有签名请求走同一条串行队列
 *
 * 后端**没有防刷**（文档 §2），所以"并发发几个请求"听起来无害。但设备签名的
 * nonce 是"每次唯一、5 分钟内不可复用"，并发只会在服务端把 nonce 撞掉、换回
 * 一堆 401 —— 而 401 在我们这边又意味着"重试一次"。串行的代价是毫秒级，
 * 却把这条最容易自伤的路径整个去掉了。
 *
 * ## 重试是有边界的
 *
 * "后端不防刷"不等于"可以随便重试"：
 * - 签名类 401 → 换一组 ts + nonce，**只重试一次**；
 * - 5xx / 网络 / 超时 → 指数退避，**最多 3 次尝试**；
 * - 400（含设备不可用）→ **不重试**，它不会因为再试一次而变好。
 */
import { app } from 'electron'

import { logDesktop } from '../desktop-log'
import type {
  AccountCommission,
  AccountLine,
  AccountUser,
  WxOrderStatus,
} from '../../shared/bridge'
import { deviceSignHeaders, looksLikeSignatureError } from './sign'

/** 两条线的入口地址（文档 §2）。行为完全一致，只有 region 标识不同。 */
export const DEFAULT_BASES: Record<AccountLine, string> = {
  cn: 'https://china.xinjianxue.com',
  seoul: 'https://www.xinjianxue.com',
}

export const API_PREFIX = '/api/agent/v1'

const REQUEST_TIMEOUT_MS = 10_000
const PING_TIMEOUT_MS = 2_000
/** 5xx / 网络类失败的重试次数（总尝试次数 = 它 + 1） */
const MAX_RETRIES = 2

// --------------------------------------------------------------------------- //
// 错误
// --------------------------------------------------------------------------- //

export type AccountErrorCode =
  | 'device-unusable'
  | 'bad-request'
  | 'need-login'
  | 'unauthorized'
  | 'signature'
  | 'recover-rejected'
  | 'forbidden'
  | 'no-account'
  | 'conflict'
  | 'unavailable'
  | 'server'
  | 'network'
  | 'timeout'
  | 'no-auth'

export class AccountApiError extends Error {
  readonly code: AccountErrorCode
  readonly status: number
  /** 后端明确说"会话过期/未登录" —— 见到它要清掉本地会话 */
  readonly needLogin: boolean
  /** 忘记密码被拒时的人工重置指引 */
  readonly manualReset?: { email: string; require: string }

  constructor(
    code: AccountErrorCode,
    message: string,
    options: {
      status?: number
      needLogin?: boolean
      manualReset?: { email: string; require: string }
    } = {},
  ) {
    super(message)
    this.name = 'AccountApiError'
    this.code = code
    this.status = options.status ?? 0
    this.needLogin = options.needLogin ?? false
    this.manualReset = options.manualReset
  }
}

function fallbackMessage(status: number): string {
  if (status === 401) return '登录状态已失效，请重新登录。'
  if (status === 403) return '这次操作被拒绝了。'
  if (status === 404) return '本设备还没有账号，请先注册。'
  if (status === 409) return '已经存在冲突的记录。'
  if (status === 503) return '服务暂时不可用，稍后再试。'
  if (status >= 500) return '服务器开小差了，请稍后重试。'
  return `请求失败（HTTP ${status}）。`
}

function toError(status: number, payload: unknown): AccountApiError {
  const data = (payload ?? {}) as Record<string, unknown>
  const raw = typeof data.error === 'string' ? data.error.trim() : ''
  const message = raw || fallbackMessage(status)
  const needLogin = data.need_login === true
  const resetRaw = data.manual_reset as { email?: unknown; require?: unknown } | undefined
  const manualReset =
    resetRaw && typeof resetRaw.email === 'string'
      ? { email: resetRaw.email, require: String(resetRaw.require ?? '') }
      : undefined

  let code: AccountErrorCode
  if (status === 400) code = /无法识别本机设备/.test(message) ? 'device-unusable' : 'bad-request'
  else if (status === 401) code = needLogin ? 'need-login' : looksLikeSignatureError(message) ? 'signature' : 'unauthorized'
  else if (status === 403) code = manualReset ? 'recover-rejected' : 'forbidden'
  else if (status === 404) code = 'no-account'
  else if (status === 409) code = 'conflict'
  else if (status === 503) code = 'unavailable'
  else if (status >= 500) code = 'server'
  else code = 'bad-request'
  return new AccountApiError(code, message, { status, needLogin, manualReset })
}

// --------------------------------------------------------------------------- //
// 地址与串行队列
// --------------------------------------------------------------------------- //

/**
 * 允许用环境变量覆盖线路入口（给本地 mock 与联调用）。
 *
 * ⚠️ **打包后的应用只接受回环地址**。这个覆盖会把带设备签名的请求连同
 * `X-Device-Sign` 一起送到指定主机，指向外部主机等于把"这台机器的账号身份"
 * 交出去 —— 真机联调只需要在开发模式改，验收脚本用的是本地 mock（127.0.0.1）。
 */
const overrideWarned = new Set<AccountLine>()

export function baseFor(line: AccountLine): string {
  const specific = line === 'cn' ? 'SOULMATE_ACCOUNT_BASE_CN' : 'SOULMATE_ACCOUNT_BASE_SEOUL'
  const raw = (process.env.SOULMATE_ACCOUNT_API_BASE || process.env[specific] || '').trim()
  if (!raw) return DEFAULT_BASES[line]
  try {
    const parsed = new URL(raw)
    const loopback = ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(parsed.hostname)
    if (app.isPackaged && !loopback) {
      if (!overrideWarned.has(line)) {
        overrideWarned.add(line)
        logDesktop(`[account] 忽略非回环的线路覆盖（打包版）：${parsed.origin}`)
      }
      return DEFAULT_BASES[line]
    }
    return parsed.origin
  } catch {
    return DEFAULT_BASES[line]
  }
}

/**
 * 串行队列：所有**带设备签名**的请求依次执行。
 *
 * 前一个失败也必须让后面的继续（`then(task, task)`）—— 否则一次网络抖动
 * 会把整条队列永久卡死，表现是"刷新按钮按了没反应"，而且只会在这台机器上复现。
 */
let chain: Promise<unknown> = Promise.resolve()

function serialize<T>(task: () => Promise<T>): Promise<T> {
  const run = chain.then(task, task)
  chain = run.catch(() => undefined)
  return run
}

// --------------------------------------------------------------------------- //
// 请求
// --------------------------------------------------------------------------- //

export interface AuthContext {
  /** 会话 token（优先；有它就不需要设备签名） */
  token?: string
  deviceFp?: string
  deviceSecret?: string
  /** 设备签名路径下，"读哪个账号"要放在查询串里 */
  account?: string
}

export interface CallOptions {
  line: AccountLine
  method: 'GET' | 'POST'
  /** 相对 API_PREFIX 的路径，如 `/account` */
  path: string
  query?: Record<string, string>
  body?: Record<string, unknown>
  auth?: AuthContext
  /** 无 session 时用设备签名（会自动串行） */
  signed?: boolean
  timeoutMs?: number
  retries?: number
  /**
   * 换一个域名发这一次请求（默认走 `baseFor(line)`）。
   *
   * 只有兑换码用它：后端文档给的兑换码域名与其它接口**不是同一个**
   * （大陆是 `chinaapi` / `api`，而账号接口在 `china`），见 `REDEEM_BASES`。
   */
  baseOverride?: string
}

interface ParsedResponse {
  status: number
  payload: unknown
}

async function sendOnce(options: CallOptions, auth: AuthContext): Promise<ParsedResponse> {
  const url = new URL((options.baseOverride ?? baseFor(options.line)) + API_PREFIX + options.path)
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value) url.searchParams.set(key, value)
  }

  const headers: Record<string, string> = { Accept: 'application/json' }
  if (auth.token) {
    headers.Authorization = `Bearer ${auth.token}`
  } else if (options.signed) {
    if (!auth.deviceSecret || !auth.deviceFp) {
      // ⚠️ 这段文案**改过**：原文是"请重启应用后重试" —— 而重启**永远修不好**
      // 这个状态，用户照着做只会一直失败（他反馈的原话就是"缺少设备凭据是什么情况"）。
      //
      // 为什么修不好：`device_secret` **只在注册响应里出现过一次**（文档 §5.4：重复注册
      // 不再下发），所以它一旦丢失（换 Windows 用户 / 重装系统 / 清空过数据目录 /
      // DPAPI 解不开旧密文）就再也换不回来 —— 而设备在后端仍有账号，`lookup` 有结果，
      // 客户端也不会再走一次"注册"。
      //
      // 唯一可行的补救（后端已上线 /account/device-key 补发口子，文档 §4.2 + §5.11）：
      // 用**账号 + 密码登录**一次（§5.5），登录成功后 `engine.ensureDeviceKey()` 会自动
      // 重新申领一把 device_secret 存回本机，设备签名接口随即恢复。把这条路写进错误里，
      // 用户才知道该做什么。
      throw new AccountApiError(
        'no-auth',
        '本机设备凭据已丢失，需要设备签名的数据（返佣、钱包）暂时取不到。' +
          '恢复方式：在「权益 → 密码与安全」里用账号密码登录一次（登录后会自动补发设备密钥）。',
      )
    }
    // ⚠️ 路径**不含查询串**（见 sign.ts 的三个坑）
    Object.assign(
      headers,
      deviceSignHeaders(auth.deviceSecret, auth.deviceFp, options.method, API_PREFIX + options.path),
    )
  }

  let body: string | undefined
  if (options.method === 'POST') {
    headers['Content-Type'] = 'application/json; charset=utf-8'
    body = JSON.stringify(options.body ?? {})
  }

  let response: Response
  try {
    response = await fetch(url, {
      method: options.method,
      headers,
      body,
      signal: AbortSignal.timeout(options.timeoutMs ?? REQUEST_TIMEOUT_MS),
    })
  } catch (error) {
    const timedOut = error instanceof Error && /abort|timeout/i.test(error.name + error.message)
    throw new AccountApiError(
      timedOut ? 'timeout' : 'network',
      timedOut ? '网络请求超时，请检查网络后重试。' : '网络连接不可用，请检查网络后重试。',
    )
  }

  const text = await response.text()
  let payload: unknown = null
  try {
    payload = text ? JSON.parse(text) : null
  } catch {
    payload = null
  }
  return { status: response.status, payload }
}

/** 发一个请求，按"有边界的重试"策略执行。 */
export async function call<T>(options: CallOptions): Promise<T> {
  const auth: AuthContext = options.auth ?? {}
  const attempts = (options.retries ?? MAX_RETRIES) + 1
  let signatureRetried = false
  let lastError: AccountApiError | null = null

  const run = async (): Promise<T> => {
    for (let index = 0; index < attempts; index += 1) {
      try {
        const { status, payload } = await sendOnce(options, auth)
        const data = (payload ?? {}) as Record<string, unknown>
        if (status >= 200 && status < 300 && data.success !== false) return data as T
        throw toError(status, payload)
      } catch (error) {
        const apiError =
          error instanceof AccountApiError
            ? error
            : new AccountApiError('network', error instanceof Error ? error.message : String(error))
        lastError = apiError

        // 签名类 401：换一组 ts + nonce 再来一次（nonce 复用、时钟偏差都是一过性的）
        if (apiError.code === 'signature' && options.signed && !signatureRetried) {
          signatureRetried = true
          continue
        }
        const retryable =
          apiError.code === 'server' || apiError.code === 'network' || apiError.code === 'timeout'
        if (!retryable) break
        if (index === attempts - 1) break
        await new Promise((resolve) => setTimeout(resolve, 400 * 2 ** index))
      }
    }
    throw lastError ?? new AccountApiError('network', '请求失败。')
  }

  return options.signed ? serialize(run) : run()
}

// --------------------------------------------------------------------------- //
// 12 个接口
// --------------------------------------------------------------------------- //

export interface PingResult {
  ok: boolean
  region: string
  server_time: number
}

export interface RateResult {
  usdt_to_token: number
  updated_at: string
}

export interface LookupResult {
  device_fp: string
  accounts: AccountUser[]
  current_account_id: number | null
}

export interface RegisterResult {
  created: boolean
  device_fp: string
  user: AccountUser
  /** 只在**首次创建**时出现一次；重复调用没有 */
  session_token?: string
  /** 同上，只在首次创建时出现一次 */
  device_secret?: string
}

export interface LoginResult {
  session_token: string
  user: AccountUser
}

export interface DeviceKeyResult {
  device_fp: string
  device_secret: string
}

export interface DeviceSessionResult {
  session_token: string
  user: AccountUser
}

/**
 * 用**设备指纹**换一个会话（本机设备身份登录，**不需要密码**）。
 *
 * 有密码的账号恢复出厂后，session 与 device_secret 一起丢；而"空密码默认登录"只对
 * 无密码账号有效 —— 有密码账号要静默补回密钥，就需要这条口子：后端用设备指纹校验
 * 本机（与 /account/lookup、/account/recover 同一个信任模型），直接签发会话。
 *
 * 产品上这是成立的：密码在本应用里只用于**官网**登录导入/导出搭子（见 SecurityCard），
 * 本机登录本来就该凭设备指纹，不设密码、设了密码都一样。
 *
 * ⚠️ 这是**后端新口子**，当前可能尚未上线：上线前调用会 404，调用方已容错
 * （engine 的 healDeviceKeyIfMissing 会静默放弃并记日志）。
 */
export function deviceSession(
  line: AccountLine,
  params: { deviceFp?: string; deviceInfo?: unknown },
): Promise<DeviceSessionResult> {
  return call<DeviceSessionResult>({
    line,
    method: 'POST',
    path: '/account/device-session',
    body: {
      ...(params.deviceFp ? { device_fp: params.deviceFp } : {}),
      ...(params.deviceInfo ? { device_info: params.deviceInfo } : {}),
    },
  })
}

/**
 * 重新申领设备密钥：**必须已登录**（会话 token）。
 *
 * `device_secret` 只在"新建账号"那一次下发，本地一旦丢失（重装、清数据、DPAPI
 * 解不开）就换不回来，而设备在后端仍有账号、不会重走注册 —— 于是返佣/钱包/改密
 * 这些要设备签名的接口全部不可用。后端为此给了这条"已登录时补发"的口子（§4.2）。
 *
 * ⚠️ 返回的明文只出现这一次，拿到必须立刻写入加密存储；不要落日志、不要进对话、
 * 不要写普通配置文件。
 */
export function claimDeviceKey(
  line: AccountLine,
  auth: AuthContext,
  params: { deviceFp?: string; deviceInfo?: unknown } = {},
): Promise<DeviceKeyResult> {
  return call<DeviceKeyResult>({
    line,
    method: 'POST',
    path: '/account/device-key',
    auth,
    // 这条口子不吃设备签名、只吃会话：signed 留 false，auth 里带了 token 就会走 Bearer
    signed: false,
    body: {
      ...(params.deviceFp ? { device_fp: params.deviceFp } : {}),
      ...(params.deviceInfo ? { device_info: params.deviceInfo } : {}),
    },
  })
}

export interface WalletResult {
  address: string
  network: string
}

export interface WatchResult extends WalletResult {
  watch: boolean
  task_id: number
  window_seconds: number
  balance_poll_seconds: number
}

export interface InviteResult {
  bonus_token: string
  inviter_masked: string | null
  invite_bound: boolean
}

export interface RecoverResult {
  account: string
}

const clientVersion = (): string => app.getVersion()

/** 线路探测 / 校时用。无鉴权，2 秒超时（探测代码自己也会计时）。 */
export function ping(line: AccountLine, timeoutMs = PING_TIMEOUT_MS): Promise<PingResult> {
  return call<PingResult>({
    line,
    method: 'GET',
    path: '/ping',
    timeoutMs,
    retries: 0,
  })
}

export function fetchRate(line: AccountLine, auth?: AuthContext): Promise<RateResult> {
  return call<RateResult>({ line, method: 'GET', path: '/rate', auth })
}

/** 查本机账号（首启最先调用）。有 device_fp 时以它为准，省一次后端重算。 */
export function lookup(
  line: AccountLine,
  params: { deviceFp?: string; deviceInfo?: unknown },
): Promise<LookupResult> {
  return call<LookupResult>({
    line,
    method: 'POST',
    path: '/account/lookup',
    body: {
      ...(params.deviceFp ? { device_fp: params.deviceFp } : {}),
      ...(params.deviceInfo ? { device_info: params.deviceInfo } : {}),
      client_version: clientVersion(),
    },
  })
}

/** 注册。**只在本机没有账号时调用**；重复调用后端会回 created:false。 */
export function register(
  line: AccountLine,
  params: { deviceFp?: string; deviceInfo?: unknown },
): Promise<RegisterResult> {
  return call<RegisterResult>({
    line,
    method: 'POST',
    path: '/register',
    body: {
      ...(params.deviceFp ? { device_fp: params.deviceFp } : {}),
      ...(params.deviceInfo ? { device_info: params.deviceInfo } : {}),
      client_version: clientVersion(),
      line,
    },
  })
}

/**
 * 登录。
 *
 * `mode: 'switch'` 用于"切到本机列表里的另一个账号"与"登录其他账号"两件事 ——
 * 它们在后端是同一个动作（把会话换成那个账号的）；`default` 留给"还用本机默认
 * 那个账号"，目前只有切换场景会走到这里，所以一律发 `switch`。
 */
export function login(
  line: AccountLine,
  params: {
    deviceInfo: unknown
    account?: string
    password?: string
    /**
     * `'default'` = 登录**本设备默认（is_primary）账号**（文档 §5.5：`account` 省略时
     * 后端自己找默认账号；本设备自动创建的账号可以**空密码**直接进入）。
     * 缺省 `'switch'`，保持既有"切账号 / 登录其他账号"的行为不变。
     */
    mode?: 'default' | 'switch'
    /**
     * 显式发送 `password: ""`（空密码进入）。
     *
     * 默认不发送 password 字段；但**静默默认登录**需要它 —— 空串被 `? :` 过滤掉
     * 之后后端收到的是"没有 password"，按缺参处理，静默登录就会被拒（0.1.37 的教训）。
     */
    emptyPassword?: boolean
  },
): Promise<LoginResult> {
  return call<LoginResult>({
    line,
    method: 'POST',
    path: '/login',
    body: {
      device_info: params.deviceInfo,
      mode: params.mode ?? 'switch',
      ...(params.account ? { account: params.account } : {}),
      ...(params.password
        ? { password: params.password }
        : params.emptyPassword
          ? { password: '' }
          : {}),
    },
  })
}

/** 账号信息。会话或设备签名（无会话时带 `?account=`）。 */
export function fetchAccount(
  line: AccountLine,
  auth: AuthContext,
): Promise<{ user: AccountUser }> {
  const signed = !auth.token
  return call<{ user: AccountUser }>({
    line,
    method: 'GET',
    path: '/account',
    query: { account: signed ? auth.account ?? '' : '' },
    auth,
    signed,
  })
}

/** 充值地址。地址终身不变，取不到时后端回 503，交给补偿流程重试。 */
export function fetchWallet(line: AccountLine, auth: AuthContext): Promise<WalletResult> {
  const signed = !auth.token
  return call<WalletResult>({
    line,
    method: 'GET',
    path: '/account/wallet',
    query: { account: signed ? auth.account ?? '' : '' },
    auth,
    signed,
  })
}

/** 让后端盯住本账号地址 45 秒（文档 §5.8）。无参数，可重复调用续盯。 */
export function watchRecharge(line: AccountLine, auth: AuthContext): Promise<WatchResult> {
  const signed = !auth.token
  return call<WatchResult>({
    line,
    method: 'POST',
    path: '/account/recharge/watch',
    body: signed ? { account: auth.account ?? '' } : {},
    auth,
    signed,
  })
}

/** 设 / 改密码。**必须走设备签名**（后端要靠它定位用户）。 */
export function setPassword(
  line: AccountLine,
  auth: AuthContext,
  params: { account: string; newPassword: string; oldPassword?: string },
): Promise<{ user: AccountUser }> {
  return call<{ user: AccountUser }>({
    line,
    method: 'POST',
    path: '/account/password',
    body: {
      account: params.account,
      new_password: params.newPassword,
      ...(params.oldPassword ? { old_password: params.oldPassword } : {}),
    },
    auth,
    signed: true,
  })
}

/** 改账号名。同样走设备签名；已被占用回 409。 */
export function renameAccount(
  line: AccountLine,
  auth: AuthContext,
  params: { account: string; newAccount: string; password?: string },
): Promise<{ user: AccountUser }> {
  return call<{ user: AccountUser }>({
    line,
    method: 'POST',
    path: '/account/name',
    body: {
      account: params.account,
      new_account: params.newAccount,
      ...(params.password ? { password: params.password } : {}),
    },
    auth,
    signed: true,
  })
}

/** 忘记密码：账号 + 设备指纹（不需要密码、不需要 device_secret）。 */
export function recoverAccount(
  line: AccountLine,
  params: { account: string; deviceInfo: unknown; newPassword: string },
): Promise<RecoverResult> {
  return call<RecoverResult>({
    line,
    method: 'POST',
    path: '/account/recover',
    body: {
      account: params.account,
      device_info: params.deviceInfo,
      new_password: params.newPassword,
    },
  })
}

/** 补填邀请码。只成功一次，之后回 409。 */
export function invite(
  line: AccountLine,
  auth: AuthContext,
  code: string,
): Promise<InviteResult> {
  const signed = !auth.token
  return call<InviteResult>({
    line,
    method: 'POST',
    path: '/account/invite',
    body: { invite_code: code, ...(signed ? { account: auth.account ?? '' } : {}) },
    auth,
    signed,
  })
}

// --------------------------------------------------------------------------- //
// 支付 / 返佣 / 提现（《微信支付接入文档》v1.0）
// --------------------------------------------------------------------------- //

export interface WxCreateResult {
  order_no: string
  amount_yuan: number
  token_amount: string
  rate_yuan_to_token: string
  commission_rate: number
  code_url: string
  expire_seconds: number
}

export interface WxQueryResult {
  order_no: string
  status: WxOrderStatus
  amount_yuan: number
  token_amount: string
  commission_rate: number
  paid_at: string | null
}

export interface WithdrawResult {
  withdraw_id?: number
  /** 实发净额（人民币为 2 位小数字符串，USDT 为 6 位小数） */
  amount: string
  gross_amount: number
  fee: string
  message: string
}

/** 微信扫码下单（大陆）。`amountYuan` 必须是整数（后端限 1~50000）。 */
export function wxCreateOrder(
  line: AccountLine,
  auth: AuthContext,
  amountYuan: number,
): Promise<WxCreateResult> {
  const signed = !auth.token
  return call<WxCreateResult>({
    line,
    method: 'POST',
    path: '/recharge/wx/create',
    body: { amount_yuan: amountYuan },
    auth,
    signed,
  })
}

/** 微信查单（大陆，轮询用）。 */
export function wxQueryOrder(
  line: AccountLine,
  auth: AuthContext,
  orderNo: string,
): Promise<WxQueryResult> {
  const signed = !auth.token
  return call<WxQueryResult>({
    line,
    method: 'GET',
    path: '/recharge/wx/query',
    query: { order_no: orderNo },
    auth,
    signed,
  })
}

/**
 * 佣金余额 + 提现记录。两类都返回，客户端按线路只展示对应那一类。
 *
 * ⚠️ `query.account` 不能省：没有会话 token 时后端只能靠**设备签名 + `?account=`**
 * 定位账号（与 `fetchAccount` / `fetchWallet` 完全同一个约定）。这里原先漏了它，
 * 于是"没拿到 token"的那条路径必然 404 —— 表现就是佣金永远是 null、界面上什么都
 * 看不到（实测反馈"返佣刷新不生效"）。签名路径带上账号名，两条路径就都能通了。
 */
/**
 * 兑换码的域名。**与其它接口不同**（后端《兑换码充值Token-前端接入说明》给的大陆
 * 是 `chinaapi` / `api` 两个域名，而账号接口在 `china`），所以它不能走 `baseFor`。
 *
 * ⚠️ 这份表与核心的 `core/src/my_agent/config/lines.py` 是**同一份事实**
 * （核心那边要用它告诉 AI"当前线路的请求接口是哪个"），改一处要改两处 ——
 * `verify:app` 有一条结构闸专门比对两者的域名集合，不一致会直接红。
 *
 * 主 + 备按序：文档给了两个大陆域名，只有**连不上**才切下一个。
 */
export const REDEEM_BASES: Record<AccountLine, string[]> = {
  cn: ['https://chinaapi.xinjianxue.com', 'https://api.xinjianxue.com'],
  seoul: ['https://www.xinjianxue.com'],
}

export interface RedeemResult {
  message: string
  unit: string
  token_amount: string
  user: { account: string; token_balance: string }
}

/**
 * 兑换码充值 Token：**一次性核销**，成功后余额立即到账。
 *
 * 两条刻意的约束（文档 §3「边界」）：
 *
 * 1. **不自动重试**：码是一次性的，重复提交必现 400「该兑换码已被使用」，
 *    重试只会让用户以为系统出错；
 * 2. **只有"连不上/服务端挂了"才换备选域名**（`status` 为 0 或 ≥500）；
 *    `兑换码不存在 / 已被使用 / 已禁用` 这类业务错误直接抛出去、原样展示。
 */
export async function redeemCode(
  line: AccountLine,
  auth: AuthContext,
  code: string,
): Promise<RedeemResult> {
  const bases = REDEEM_BASES[line] ?? REDEEM_BASES.cn
  let lastError: unknown = null
  for (const base of bases) {
    try {
      return await call<RedeemResult>({
        line,
        method: 'POST',
        path: '/redeem',
        auth,
        signed: !auth.token,
        body: { code: code.trim() },
        baseOverride: base,
        retries: 0,
      })
    } catch (error) {
      lastError = error
      const status = error instanceof AccountApiError ? error.status : 0
      if (status > 0 && status < 500) throw error
      logDesktop(`[account] 兑换码域名不可用（${base}，status=${status}），试下一个`)
    }
  }
  throw lastError ?? new AccountApiError('network', '兑换码服务暂时连不上，请稍后重试。')
}

export function fetchCommission(
  line: AccountLine,
  auth: AuthContext,
): Promise<AccountCommission> {
  const signed = !auth.token
  return call<AccountCommission>({
    line,
    method: 'GET',
    path: '/commission/me',
    query: { account: signed ? auth.account ?? '' : '' },
    auth,
    signed,
  })
}

/**
 * 人民币提现（大陆）。`payee` 是收款账号，字段名与 `method` 一致
 * （zhifubao / bank），首次使用该方式时后端要求带上。
 */
export function withdrawRmb(
  line: AccountLine,
  auth: AuthContext,
  payload: { amount: number; method: string; payee: string },
): Promise<WithdrawResult> {
  const signed = !auth.token
  // payee 留空时**不带该字段**：用户可能已经填过收款方式（后端从账号资料读），
  // 硬塞一个空字符串反而会被当成"这次要清空它"
  return call<WithdrawResult>({
    line,
    method: 'POST',
    path: '/withdraw/apply',
    body: {
      amount: payload.amount,
      method: payload.method,
      ...(payload.payee ? { [payload.method]: payload.payee } : {}),
    },
    auth,
    signed,
  })
}

/** USDT 提现（国际）。`trc20_address` 需 T 开头 34 位，固定 1 USDT/次手续费。 */
export function withdrawUsdt(
  line: AccountLine,
  auth: AuthContext,
  payload: { amount: number; trc20_address: string },
): Promise<WithdrawResult> {
  const signed = !auth.token
  return call<WithdrawResult>({
    line,
    method: 'POST',
    path: '/withdraw/usdt/apply',
    body: { amount: payload.amount, trc20_address: payload.trc20_address },
    auth,
    signed,
  })
}

// --------------------------------------------------------------------------- //
// PayPal 充值（首尔线路专有）
//
// ⚠️ 价格、数量上下限、client_id、mode **全部以服务端下发为准**，前端不写死：
// 汇率与限额是运营随时会调的参数，写死就意味着"后端调了价，界面还在按旧价试算"，
// 用户按旧价付了钱却拿到对不上的 Token —— 这类账目偏差无法自愈，只能靠不写死来避免。
// --------------------------------------------------------------------------- //

/**
 * PayPal 渠道配置。字段全部可选：后端版本不同可能少给某个键，
 * 调用方（engine）负责补安全默认值（min=1 / max=100），不要把默认值放这里 ——
 * 这里只忠实转发服务端答应了什么。
 *
 * ⚠️ 服务端的字段名与内部口径**不同名**（产品以文档为准给的映射）：
 * ``unit_tokens``（每份到账 Token）→ 内部 ``unit_price``；
 * ``max_quantity``（单次上限）→ 内部 ``max``；
 * ``unit_usd``（每份美元单价）→ 内部 ``unit_usd``（应付 = 份数 × 它）。
 * 映射收在 engine.loadPaypalConfig 一处，本接口把原始字段原样带出来即可 ——
 * 这样服务端与网页线口径都不用动，改名成本由客户端一层消化。
 */
export interface PaypalConfigResult {
  /** 每份到账 Token 数（服务端原始字段 unit_tokens） */
  unit_tokens?: number
  /** 兼容旧字段名（早期客户端按 unit_price 取） */
  unit_price?: number
  /** 每份美元单价（服务端原始字段） */
  unit_usd?: number
  /** 单次可购数量的下限 / 上限（上限的服务端原始字段是 max_quantity） */
  min?: number
  max?: number
  max_quantity?: number
  /** PayPal 前端 SDK 的 client_id（结账页由后端下发，客户端不持有） */
  client_id?: string
  /** 运行模式，如 sandbox / live */
  mode?: string
  currency?: string
}

/**
 * 下单结果：**一次性结账令牌 `ct`** + 结账跳转地址。
 *
 * ⚠️ 口径以《客户端PayPal充值-前端配置说明（方案 B·最终版）》为准：
 * 客户端只调 `POST /paypal/session` —— 拿回的 `ct` 既是"这张结账页的取件码"，
 * 也是后续轮询到没到账的凭证；`POST /checkout/create` 与 `POST /checkout/capture`
 * 是**结账页自己内部**调的，客户端不碰。
 *
 * 旧的实现（0.1.43~0.1.53）直接调 `checkout/create` 拿 `order_id`，服务端不认这条路，
 * 回 400「支付链接已失效，请重新发起」—— 这就是 0.1.53 收款走不通的根因。
 */
export interface PaypalSessionResult {
  /** 一次性结账令牌：绑用户、绑数量、过期时间见 `expires_in` */
  ct: string
  /** 优先用它 */
  checkout_url?: string
  /** 兼容另一种命名 */
  approve_url?: string
  /** 服务端回认的份数 / 应付 / 币种 —— 与本地试算同口径，可用来核对 */
  quantity?: number
  amount?: string
  currency?: string
  tokens?: number
  unit_usd?: number
  unit_tokens?: number
  max_quantity?: number
  /** 结账链接有效期（秒）。缺省时主进程按 1800 兜底，绝不写死成"30 分钟" */
  expires_in?: number
}

/**
 * 查单结果（轮询用）。
 *
 * `already` 表示这笔订单此前已经入账过（用户重复点了付款 / 上一轮没刷到），
 * 直接刷新余额即可 —— 不需要、也不允许再走一次加 Token 的逻辑。
 * `token_amount` / `token_balance` 只在已入账时出现，用于把到账金额写进日志。
 */
export interface PaypalStatusResult {
  paid: boolean
  already: boolean
  status: string
  token_amount?: string
  token_balance?: string
}

/** 取 PayPal 渠道配置（单价 / 限额 / client_id / 模式）。 */
export function paypalConfig(line: AccountLine, auth: AuthContext): Promise<PaypalConfigResult> {
  const signed = !auth.token
  return call<PaypalConfigResult>({
    line,
    method: 'GET',
    path: '/paypal/config',
    auth,
    signed,
  })
}

/** 创建 PayPal 结账会话：`quantity` 是**购买份数**（份数 × 单价 = 应付美元）。 */
export function paypalSession(
  line: AccountLine,
  auth: AuthContext,
  params: { quantity: number },
): Promise<PaypalSessionResult> {
  const signed = !auth.token
  return call<PaypalSessionResult>({
    line,
    method: 'POST',
    path: '/paypal/session',
    body: { quantity: params.quantity },
    auth,
    signed,
  })
}

/**
 * 查询结账状态（主进程每 3 秒轮询一次，见 engine 的 PayPal 轮询）。
 *
 * ⚠️ 参数是 `ct` 而**不是** `order_id`：`status` 会以订单表为准补记一次
 * （webhook 单独到账时 ct 表可能还是 open），所以 ct 必须在主进程手里留到本轮结束。
 */
export function paypalStatus(
  line: AccountLine,
  auth: AuthContext,
  params: { ct: string },
): Promise<PaypalStatusResult> {
  const signed = !auth.token
  return call<PaypalStatusResult>({
    line,
    method: 'GET',
    path: '/paypal/checkout/status',
    query: { ct: params.ct },
    auth,
    signed,
  })
}
