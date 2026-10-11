/**
 * 账号凭据的加密存储（`device_secret` / `session_token`）。
 *
 * ## 为什么不复用 `electron/secrets.ts` 的 SecretsStore
 *
 * 它的键空间是**固定的三类**（`models` / `mcp` / `integrations`），`normalize()`
 * 只重建这三个键、其余顶层键会被直接丢掉。把账号凭据塞进去不会报错，只会被
 * **静默丢弃** —— 而"凭据丢了"这件事要到下次需要用的时候才暴露，那时
 * `device_secret` 已经补不回来了（文档 §4.2：它只在注册响应里出现一次）。
 *
 * 所以这里单开一份文件，沿用与它**完全相同的落盘格式与安全策略**，
 * 只是键空间只有两个：
 *
 * - `safeStorage.encryptString()`（Windows 上是 DPAPI，与当前 Windows 用户绑定）；
 * - 系统不支持加密时降级明文并在日志里明确告警 —— 宁可让人知道风险，
 *   也不要假装安全（与 secrets.ts 同一取舍）；
 * - 先写临时文件再改名：直接覆写时中途断电会留下半截密文，那份凭据就永久解不开了。
 *
 * ⚠️ 这两个值**永远不跨 IPC**：渲染层只拿到"有没有"（`AccountSnapshot.hasDeviceSecret`
 * / `loggedIn`），拿不到值本身。
 */
import fs from 'node:fs'
import path from 'node:path'

import { app, safeStorage } from 'electron'

import { logDesktop } from '../desktop-log'

const SECRETS_FILE = 'account-secrets.bin'
const FORMAT_VERSION = 1

/** 账号凭据只有这两个键；写成联合类型，防止将来随手往里加东西 */
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
      // 常见于换了 Windows 用户 / 重装系统：DPAPI 解不开旧密文。
      // **不删文件**：留着才有恢复余地（与 secrets.ts 一致）。
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

  /**
   * 写入。**空值等于清除** —— 与密钥库的"空值忽略"语义相反，这里是有意的：
   * 会话过期时必须能把它清掉（`need_login` 那条路），否则我们会一直拿着一个
   * 无效 token 去请求，每一次都被拒。
   */
  set(name: AccountSecretName, value: string | null): void {
    const next: AccountSecrets = { ...this.load() }
    if (value) next[name] = value
    else delete next[name]
    this.persist(next)
  }
}
