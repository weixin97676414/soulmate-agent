
















import { app } from 'electron'

import { logDesktop } from '../desktop-log'
import type {
  AccountCommission,
  AccountLine,
  AccountUser,
  WxOrderStatus,
} from '../../shared/bridge'
import { deviceSignHeaders, looksLikeSignatureError } from './sign'


export const DEFAULT_BASES: Record<AccountLine, string> = {
  cn: 'https://china.xinjianxue.com',
  seoul: 'https://www.xinjianxue.com',
}

export const API_PREFIX = '/api/agent/v1'

const REQUEST_TIMEOUT_MS = 10_000
const PING_TIMEOUT_MS = 2_000

const MAX_RETRIES = 2





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
  
  readonly needLogin: boolean
  
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







let chain: Promise<unknown> = Promise.resolve()

function serialize<T>(task: () => Promise<T>): Promise<T> {
  const run = chain.then(task, task)
  chain = run.catch(() => undefined)
  return run
}





export interface AuthContext {
  
  token?: string
  deviceFp?: string
  deviceSecret?: string
  
  account?: string
}

export interface CallOptions {
  line: AccountLine
  method: 'GET' | 'POST'
  
  path: string
  query?: Record<string, string>
  body?: Record<string, unknown>
  auth?: AuthContext
  
  signed?: boolean
  timeoutMs?: number
  retries?: number
  





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
      
      
      
      
      
      
      
      
      
      
      
      
      throw new AccountApiError(
        'no-auth',
        '本机设备凭据已丢失，需要设备签名的数据（返佣、钱包）暂时取不到。' +
          '恢复方式：在「权益 → 密码与安全」里用账号密码登录一次（登录后会自动补发设备密钥）。',
      )
    }
    
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
  
  session_token?: string
  
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








export function login(
  line: AccountLine,
  params: {
    deviceInfo: unknown
    account?: string
    password?: string
    




    mode?: 'default' | 'switch'
    





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
  
  amount: string
  gross_amount: number
  fee: string
  message: string
}


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





export function withdrawRmb(
  line: AccountLine,
  auth: AuthContext,
  payload: { amount: number; method: string; payee: string },
): Promise<WithdrawResult> {
  const signed = !auth.token
  
  
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





















export interface PaypalConfigResult {
  
  unit_tokens?: number
  
  unit_price?: number
  
  unit_usd?: number
  
  min?: number
  max?: number
  max_quantity?: number
  
  client_id?: string
  
  mode?: string
  currency?: string
}












export interface PaypalSessionResult {
  
  ct: string
  
  checkout_url?: string
  
  approve_url?: string
  
  quantity?: number
  amount?: string
  currency?: string
  tokens?: number
  unit_usd?: number
  unit_tokens?: number
  max_quantity?: number
  
  expires_in?: number
}








export interface PaypalStatusResult {
  paid: boolean
  already: boolean
  status: string
  token_amount?: string
  token_balance?: string
}


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
