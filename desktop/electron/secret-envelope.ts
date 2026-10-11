/**
 * 密钥文件的**共享封套**：加解密 + 原子落盘 + 脱敏预览。
 *
 * ## 消费方
 *
 * `secrets.ts`（模型 API Key / MCP 环境变量 / 集成凭据，存 `secrets.bin`）
 * 与 `skill-secrets.ts`（用户经 `request_secret` 交给技能的密钥，存 `skill-secrets.bin`）。
 * 两个 store **仍然是两条互不相干的链路**（键空间与 normalize 各归各的，
 * 见 `skill-secrets.ts` 文件头那张表），这里只收拢**它们必须逐字一致**的那部分。
 *
 * ## 为什么要收拢（第 86 批 B 组，M-17）
 *
 * 同一套原语原来在两处各写一遍，而且**已经漂移**：
 * - 脱敏阈值一个 `<= 8`、一个 `<= 10`，而 `skill-secrets` 的注释还写着"与 `secrets.ts`
 *   的 mask() 同一个口径"——注释是假的。Python 侧 `ModelSpec.masked_api_key()` 用的是
 *   `<= 8`，而**掩码串是"这个 Key 用户没改过"的兜底判据**（见 `models.py` 的
 *   `_preserve_api_keys`）：两边不一致的后果是掩码串被当成真 Key 写进配置，
 *   症状是"保存后立刻连不上、重启又好了"。
 * - `secrets.ts` 写临时文件带 `mode: 0o600`，`skill-secrets.ts` 没有。
 *
 * ⇒ 这几条**必须逐字一致**的东西集中到这里；两个 store 只保留各自的
 * 键空间、`normalize` 与合并语义。
 *
 * ⚠️ 这里**不做任何 format 迁移**：封套结构 `{v, encrypted, data}` 与
 * `safeStorage.encryptString()`（Windows 即 DPAPI、绑定当前 Windows 用户）
 * 都是原样搬过来的，磁盘上已有的密钥文件照旧能读。
 */
import fs from 'node:fs'
import path from 'node:path'

import { safeStorage } from 'electron'

/** 封套格式版本。两个 store 共用同一个值（它们各写各的文件，版本号只是给将来迁移用）。 */
export const SECRETS_FORMAT_VERSION = 1

export interface StoredEnvelope {
  v: number
  encrypted: boolean
  /** 加密时是 base64 密文，否则是原样 JSON 字符串 */
  data: string
}

/**
 * 读取并解开封套，返回里面的 JSON 值；**任何失败都返回 `null`**。
 *
 * ⚠️ **绝不删文件**：解密失败常见于"换了 Windows 用户 / 重装系统"（DPAPI 解不开
 * 旧密文），但"解不开"也可能是**临时的**（当前 safeStorage 还没就绪）。删了就永久
 * 没有恢复余地，而留着它用户换回原环境还能救。
 *
 * `label` 只用于日志前缀（`secrets` / `skill-secrets`）。
 */
export function readSecretFile(filePath: string, label: string): unknown {
  let raw: string
  try {
    raw = fs.readFileSync(filePath, 'utf-8')
  } catch {
    // 文件不存在是**常态**（用户还没配过任何密钥），不当错误
    return null
  }

  let envelope: StoredEnvelope
  try {
    envelope = JSON.parse(raw) as StoredEnvelope
  } catch (error) {
    console.error(`[${label}] 密钥文件损坏，按空处理:`, error)
    return null
  }
  if (!envelope?.data) return null

  try {
    const text = envelope.encrypted
      ? safeStorage.decryptString(Buffer.from(envelope.data, 'base64'))
      : envelope.data
    return JSON.parse(text) as unknown
  } catch (error) {
    console.error(`[${label}] 密钥解密失败（可能换了系统用户），按空处理:`, error)
    return null
  }
}

/**
 * 加密并**原子**写入，返回"这次是否加密"。
 *
 * 先写 `.tmp` 再 `rename`：直接覆写时若中途断电会留下半截密文，
 * 那份密钥就**永久解不开**了。
 *
 * ⚠️ IO 失败**照旧抛出**（不在这里吞掉）：调用方是主进程的 IPC handler，
 * 让它失败、让用户看到"没保存上"，好过静默地以为存了。
 * 系统不支持加密时降级明文（调用方会把 `protection` 报成 `plaintext` 并在界面上警告）。
 */
export function writeSecretFile(filePath: string, payload: unknown, _label: string): boolean {
  const text = JSON.stringify(payload)
  const encrypted = safeStorage.isEncryptionAvailable()
  const envelope: StoredEnvelope = {
    v: SECRETS_FORMAT_VERSION,
    encrypted,
    data: encrypted ? safeStorage.encryptString(text).toString('base64') : text,
  }
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  const tmp = `${filePath}.tmp`
  // mode 0o600：只有当前用户可读（另一处以前漏了这个）
  fs.writeFileSync(tmp, JSON.stringify(envelope, null, 2), { encoding: 'utf-8', mode: 0o600 })
  fs.renameSync(tmp, filePath)
  return encrypted
}

/**
 * 生成密钥的脱敏预览。
 *
 * **返回值里必须带 `*`** —— 渲染层靠这一点判断"这不是真值，保存时不要提交"。
 * 如果预览长得像真 Key，用户点一次保存就会把预览本身写进密钥库，把真 Key 覆盖掉，
 * 而且症状是"下次启动 Key 失效了"，很难联想到是预览格式的问题。
 *
 * ⚠️ **格式与阈值必须与 Python 侧 `ModelSpec.masked_api_key()`
 * （`core/src/my_agent/config/schemas.py`）逐字符一致**：前 4 位 + 6 个星 + 后 4 位，
 * 长度 `<= 8` 时整体打码。两边曾经不一致，后果是"这个 Key 用户没改过"的判据失效。
 * Python 侧有回归钉：`core/tests/unit/test_model_api_key_preserve.py::test_mask_format_is_stable`。
 */
export function maskSecret(value: string): string {
  if (!value) return ''
  // 太短的值截取头尾会几乎还原出原文，整体打码
  if (value.length <= 8) return '*'.repeat(value.length)
  return `${value.slice(0, 4)}${'*'.repeat(6)}${value.slice(-4)}`
}
