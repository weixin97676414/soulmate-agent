




















import fs from 'node:fs'
import path from 'node:path'

import { app, safeStorage } from 'electron'

import { logDesktop } from '../desktop-log'

const SECRETS_FILE = 'account-secrets.bin'
const FORMAT_VERSION = 1


export type AccountSecretName = 'device_secret' | 'session_token'

interface StoredEnvelope {
  v: number
  encrypted: boolean
  data: string
}

type AccountSecrets = Partial<Record<AccountSecretName, string>>

function normalize(raw: unknown): AccountSecrets {
  if (!raw || typeof raw !== 'object') return {}
  const source = raw as Record<string, unknown>
  const payload: AccountSecrets = {}
  for (const name of ['device_secret', 'session_token'] as const) {
    const value = source[name]
    if (typeof value === 'string' && value) payload[name] = value
  }
  return payload
}

export class AccountSecretStore {
  private cached: AccountSecrets | null = null

  private get filePath(): string {
    return path.join(app.getPath('userData'), SECRETS_FILE)
  }

  private load(): AccountSecrets {
    if (this.cached) return this.cached
    let envelope: StoredEnvelope | null = null
    try {
      if (fs.existsSync(this.filePath)) {
        envelope = JSON.parse(fs.readFileSync(this.filePath, 'utf-8')) as StoredEnvelope
      }
    } catch (error) {
      console.error('[account] 账号凭据文件损坏，按空处理:', error)
    }
    if (!envelope?.data) {
      this.cached = {}
      return this.cached
    }
    try {
      this.cached = normalize(
        JSON.parse(
          envelope.encrypted ? safeStorage.decryptString(Buffer.from(envelope.data, 'base64')) : envelope.data,
        ),
      )
    } catch (error) {
      
      
      console.error('[account] 账号凭据解密失败（可能换了系统用户），按空处理:', error)
      this.cached = {}
    }
    return this.cached
  }

  private persist(payload: AccountSecrets): void {
    this.cached = payload
    let envelope: StoredEnvelope
    if (safeStorage.isEncryptionAvailable()) {
      const encrypted = safeStorage.encryptString(JSON.stringify(payload))
      envelope = { v: FORMAT_VERSION, encrypted: true, data: encrypted.toString('base64') }
    } else {
      envelope = { v: FORMAT_VERSION, encrypted: false, data: JSON.stringify(payload) }
      logDesktop('[account] 系统未提供加密能力，账号凭据以明文保存')
    }
    fs.mkdirSync(path.dirname(this.filePath), { recursive: true })
    const tmp = `${this.filePath}.tmp`
    fs.writeFileSync(tmp, JSON.stringify(envelope), { encoding: 'utf-8', mode: 0o600 })
    fs.renameSync(tmp, this.filePath)
  }

  get(name: AccountSecretName): string {
    return this.load()[name] ?? ''
  }

  has(name: AccountSecretName): boolean {
    return Boolean(this.get(name))
  }

  




  set(name: AccountSecretName, value: string | null): void {
    const next: AccountSecrets = { ...this.load() }
    if (value) next[name] = value
    else delete next[name]
    this.persist(next)
  }
}
