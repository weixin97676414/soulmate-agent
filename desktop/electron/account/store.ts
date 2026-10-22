
















import fs from 'node:fs'
import path from 'node:path'

import { app } from 'electron'

import type { AccountLineState, AccountUser } from '../../shared/bridge'
import type { DeviceInfo } from './device'

const STORE_FILE = 'account.json'
const FORMAT_VERSION = 1










export interface PendingAction {
  kind: 'register' | 'lookup' | 'invite'
  
  code?: string
  at: number
}

export interface AccountData {
  deviceInfo: DeviceInfo | null
  deviceFp: string
  line: AccountLineState | null
  accounts: AccountUser[]
  currentId: number | null
  






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
      
      
      this.cached = normalize(parsed)
    } catch (error) {
      console.error('[account] 账号状态文件损坏，按空处理:', error)
      this.cached = emptyAccountData()
    }
    return this.cached
  }

  
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
      
      console.error('[account] 账号状态写入失败:', error)
    }
    return next
  }

  
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
