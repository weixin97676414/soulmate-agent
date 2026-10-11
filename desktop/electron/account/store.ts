/**
 * 账号的**明文**本地状态（`account.json`）。
 *
 * 文档 §9 把"可以明文存"和"必须加密存"分得很清楚，这里照着分：
 *
 * - 明文（本文件）：`device_info`、`device_fp`、账号列表、当前账号、充值地址、
 *   费率、线路结论、待重试队列。它们要么是**重装后查号要用**（`device_info`），
 *   要么需要在离线时也能展示（地址、费率）——加密了反而读不到；
 * - 加密（`secure.ts`）：`device_secret`、`session_token`。
 *
 * ## 两个稳定性细节
 *
 * 1. **先写临时文件再改名**：否则断电会留下半截 JSON，下次启动整份状态丢失 ——
 *    表现是"账号又变回没登录"，而用户完全不知道发生了什么；
 * 2. **读进来先归一化**：文件可能被手改过（或来自旧版本）。这里对每个字段都
 *    验一遍类型，坏字段直接丢掉而不是让整个引擎崩掉。
 */
import fs from 'node:fs'
import path from 'node:path'

import { app } from 'electron'

import type { AccountLineState, AccountUser } from '../../shared/bridge'
import type { DeviceInfo } from './device'

const STORE_FILE = 'account.json'
const FORMAT_VERSION = 1

/**
 * 待重试的动作。
 *
 * 只收**幂等**的动作：注册（重复调用返回 created:false）、查号、补邀请码
 * （已绑定会回 409，按"已完成"处理）、续盯充值。
 *
 * 刻意**不**把改密码 / 改账号名 / 登录放进来：它们要么改状态要么需要用户当场
 * 看着结果，等联网后悄悄替他执行一遍，是比"这次没成功"更糟的结果。
 */
export interface PendingAction {
  kind: 'register' | 'lookup' | 'invite'
  /** kind=invite 时要补填的码 */
  code?: string
  at: number
}

export interface AccountData {
  deviceInfo: DeviceInfo | null
  deviceFp: string
  line: AccountLineState | null
  accounts: AccountUser[]
  currentId: number | null
  /**
   * 当前这个会话 token 属于哪个账号。
   *
   * 必须有它，否则切换账号时会串号：会话 A 的 token 还在手上，界面上已经切到账号 B，
   * 这时去读 `/account` 拿到的是 **A 的**余额和地址，然后我们会用它覆盖界面上
   * B 的余额 —— 用户看到的数字是真的，只是属于另一个人（而且是另一个人的充值地址）。
   */
  sessionAccountId: number | null
  rate: number | null
  pending: PendingAction[]
}

export function emptyAccountData(): AccountData {
  return {
    deviceInfo: null,
    deviceFp: '',
    line: null,
    accounts: [],
    currentId: null,
    sessionAccountId: null,
    rate: null,
    pending: [],
  }
}

function normalizeUser(raw: unknown): AccountUser | null {
  if (!raw || typeof raw !== 'object') return null
  const source = raw as Record<string, unknown>
  const id = typeof source.id === 'number' ? source.id : Number(source.id)
  const account = typeof source.account === 'string' ? source.account.trim() : ''
  if (!Number.isFinite(id) || !account) return null
  const user: AccountUser = {
    id,
    account,
    has_password: source.has_password === true,
    my_invite_code: typeof source.my_invite_code === 'string' ? source.my_invite_code : '',
    invite_bound: source.invite_bound === true,
    // 金额是字符串：转成 number 再存会让 6 位小数被浮点吃掉的概率随缘出现
    token_balance: typeof source.token_balance === 'string' ? source.token_balance : '0.000000',
    tron_address: typeof source.tron_address === 'string' ? source.tron_address : '',
    created_at: typeof source.created_at === 'string' ? source.created_at : '',
  }
  if (source.is_primary === true) user.is_primary = true
  if (typeof source.last_used_at === 'string') user.last_used_at = source.last_used_at
  if (typeof source.inviter_masked === 'string' || source.inviter_masked === null) {
    user.inviter_masked = source.inviter_masked as string | null
  }
  return user
}

function normalizeLine(raw: unknown): AccountLineState | null {
  if (!raw || typeof raw !== 'object') return null
  const source = raw as Record<string, unknown>
  const preferred = source.preferred === 'seoul' ? 'seoul' : source.preferred === 'cn' ? 'cn' : null
  if (!preferred) return null
  const measurements: Record<string, number | null> = {}
  const rawMeasurements = (source.measurements ?? {}) as Record<string, unknown>
  for (const line of ['cn', 'seoul']) {
    const value = rawMeasurements[line]
    measurements[line] = typeof value === 'number' && Number.isFinite(value) ? value : null
  }
  return {
    preferred,
    measurements,
    updatedAt: typeof source.updatedAt === 'number' ? source.updatedAt : 0,
    manual: source.manual === true,
  }
}

function normalizeDevice(raw: unknown): DeviceInfo | null {
  if (!raw || typeof raw !== 'object') return null
  const source = raw as Record<string, unknown>
  const text = (value: unknown): string => (typeof value === 'string' ? value : '')
  const macs = Array.isArray(source.macs)
    ? source.macs.filter((mac): mac is string => typeof mac === 'string' && mac.length > 0)
    : []
  return {
    machine_guid: text(source.machine_guid),
    smbios_uuid: text(source.smbios_uuid),
    board_serial: text(source.board_serial),
    cpu_id: text(source.cpu_id),
    disk_serial: text(source.disk_serial),
    macs,
  }
}

function normalize(raw: unknown): AccountData {
  const data = emptyAccountData()
  if (!raw || typeof raw !== 'object') return data
  const source = raw as Record<string, unknown>

  data.deviceInfo = normalizeDevice(source.deviceInfo)
  data.deviceFp = typeof source.deviceFp === 'string' ? source.deviceFp : ''
  data.line = normalizeLine(source.line)
  data.accounts = Array.isArray(source.accounts)
    ? source.accounts
        .map(normalizeUser)
        .filter((user): user is AccountUser => user !== null)
    : []
  data.currentId = typeof source.currentId === 'number' ? source.currentId : null
  data.sessionAccountId =
    typeof source.sessionAccountId === 'number' ? source.sessionAccountId : null
  data.rate = typeof source.rate === 'number' && source.rate > 0 ? source.rate : null
  data.pending = Array.isArray(source.pending)
    ? source.pending
        .map((item) => {
          const entry = item as Record<string, unknown>
          const kind = entry.kind
          if (kind !== 'register' && kind !== 'lookup' && kind !== 'invite') {
            return null
          }
          const action: PendingAction = {
            kind,
            at: typeof entry.at === 'number' ? entry.at : 0,
          }
          if (typeof entry.code === 'string') action.code = entry.code
          return action
        })
        .filter((item): item is PendingAction => item !== null)
    : []
  return data
}

export class AccountStore {
  private cached: AccountData | null = null

  private get filePath(): string {
    return path.join(app.getPath('userData'), STORE_FILE)
  }

  load(): AccountData {
    if (this.cached) return this.cached
    try {
      const text = fs.existsSync(this.filePath) ? fs.readFileSync(this.filePath, 'utf-8') : ''
      const parsed = text ? (JSON.parse(text) as Record<string, unknown>) : null
      // 文件里带 `v`，但这里**不做版本分支**：现在只有 v1，而归一化本身对
      // 任何结构都是安全的（坏字段被丢掉）。等真要迁移时再照着 `v` 写分支。
      this.cached = normalize(parsed)
    } catch (error) {
      console.error('[account] 账号状态文件损坏，按空处理:', error)
      this.cached = emptyAccountData()
    }
    return this.cached
  }

  /** 局部更新并落盘，返回更新后的完整状态（调用方直接用返回值，别再读一次）。 */
  patch(partial: Partial<AccountData>): AccountData {
    const next: AccountData = { ...this.load(), ...partial }
    this.cached = next
    try {
      fs.mkdirSync(path.dirname(this.filePath), { recursive: true })
      const envelope = { v: FORMAT_VERSION, ...next }
      const tmp = `${this.filePath}.tmp`
      fs.writeFileSync(tmp, JSON.stringify(envelope, null, 2), { encoding: 'utf-8', mode: 0o600 })
      fs.renameSync(tmp, this.filePath)
    } catch (error) {
      // 落盘失败不该中断这次操作：内存里已经是新值，用户这次动作是成功的
      console.error('[account] 账号状态写入失败:', error)
    }
    return next
  }

  /** 加入待重试队列（同 kind + 同 code 不重复排队） */
  addPending(action: PendingAction): void {
    const pending = this.load().pending
    const duplicated = pending.some(
      (item) => item.kind === action.kind && (item.code ?? '') === (action.code ?? ''),
    )
    if (duplicated) return
    this.patch({ pending: [...pending, action] })
  }

  removePending(kind: PendingAction['kind'], code?: string): void {
    const pending = this.load().pending.filter(
      (item) => !(item.kind === kind && (item.code ?? '') === (code ?? '')),
    )
    this.patch({ pending })
  }
}
