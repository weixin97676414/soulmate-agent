/**
 * 密钥的安全存储。
 *
 * ## 为什么由主进程来管
 *
 * 渲染层是不可信边界（它要渲染模型输出、Markdown、上传的文件），
 * 而 API Key 一旦被注入的脚本读到就能被外传。所以：
 * **只有主进程持有密钥**，渲染层通过受限 IPC 按需取用，
 * Python 核心只在启动时通过一次性临时文件拿到。
 *
 * ## 存放方式
 *
 * `safeStorage.encryptString()` 在 Windows 上走 DPAPI，密钥与当前 Windows 用户绑定：
 * 把 `secrets.bin` 拷到别的机器或别的用户下都解不开。系统不支持加密时降级为
 * 明文并在界面上明确警告——宁可让用户知道风险，也不要假装安全。
 *
 * ## 传给 Python 的方式：临时文件 + 路径
 *
 * 环境变量会被子进程继承，而核心进程会 spawn MCP Server，密钥会直接漏给第三方进程。
 * 改成传路径：核心读完立即删除，且只有它知道路径。
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { app, safeStorage } from 'electron'

import type {
  RevealTarget,
  SecretsPatch,
  SecretsPayload,
  SecretsStatus,
} from '../shared/bridge'
import { maskSecret, readSecretFile, writeSecretFile } from './secret-envelope'

const SECRETS_FILE = 'secrets.bin'

/** 与后端 `config/secrets.py:is_secret_key` 保持一致 */
const SECRET_KEY_HINT = /key|token|secret|password|passwd|credential|auth/i

export function emptySecrets(): SecretsPayload {
  return { models: {}, mcp: {}, integrations: {} }
}

/**
 * 生成密钥的脱敏预览。
 *
 * **返回值里必须带 `*`** —— 渲染层靠这一点判断"这不是真值，保存时不要提交"
 * （见 ModelSettings.tsx 里对 keyed 的过滤）。如果预览长得像真 Key，
 * 用户点一次保存就会把预览本身写进密钥库，把真 Key 覆盖掉，
 * 而且症状是"下次启动 Key 失效了"，很难联想到是预览格式的问题。
 */
// 脱敏预览 `maskSecret()`、封套读写 `readSecretFile / writeSecretFile` 都在
// `secret-envelope.ts` —— 它们必须与 `skill-secrets.ts` 以及 Python 侧
// `ModelSpec.masked_api_key()` **逐字一致**，所以只留一份实现。

function normalize(raw: unknown): SecretsPayload {
  const payload = emptySecrets()
  if (!raw || typeof raw !== 'object') return payload
  const source = raw as Partial<SecretsPayload>

  if (source.models && typeof source.models === 'object') {
    for (const [key, value] of Object.entries(source.models)) {
      if (typeof value === 'string' && value) payload.models[key] = value
    }
  }
  if (source.mcp && typeof source.mcp === 'object') {
    for (const [server, env] of Object.entries(source.mcp)) {
      if (!env || typeof env !== 'object') continue
      const cleaned: Record<string, string> = {}
      for (const [name, value] of Object.entries(env)) {
        if (typeof value === 'string' && value) cleaned[name] = value
      }
      if (Object.keys(cleaned).length > 0) payload.mcp[server] = cleaned
    }
  }
  if (source.integrations && typeof source.integrations === 'object') {
    for (const [name, fields] of Object.entries(source.integrations)) {
      if (!fields || typeof fields !== 'object') continue
      const cleaned: Record<string, string> = {}
      for (const [key, value] of Object.entries(fields)) {
        if (typeof value === 'string' && value) cleaned[key] = value
      }
      if (Object.keys(cleaned).length > 0) payload.integrations[name] = cleaned
    }
  }
  return payload
}

export class SecretsStore {
  private cached: SecretsPayload | null = null
  private tempFile: string | null = null

  private get filePath(): string {
    return path.join(app.getPath('userData'), SECRETS_FILE)
  }

  get relativePath(): string {
    return SECRETS_FILE
  }

  // ------------------------------------------------------------------ //
  // 读写
  // ------------------------------------------------------------------ //
  load(): SecretsPayload {
    if (this.cached) return this.cached
    // 读不到 / 解不开一律按空处理，**绝不删文件**（理由见 `readSecretFile`）
    const raw = readSecretFile(this.filePath, 'secrets')
    this.cached = raw === null ? emptySecrets() : normalize(raw)
    return this.cached
  }

  save(payload: SecretsPayload): SecretsStatus {
    const normalized = normalize(payload)
    this.cached = normalized
    writeSecretFile(this.filePath, normalized, 'secrets')
    return this.status()
  }

  /**
   * 增量合并。
   *
   * ⚠️ **空值一律忽略，绝不删除。** 删除只能靠 `removeModelIds` /
   * `removeMcpVars` 显式声明。
   *
   * 这条规则是被一个反复复现的线上问题逼出来的：以前"空串 = 删除"，
   * 于是渲染层任何一次"把空值当成新值提交"（自动保存时输入框恰好为空、
   * 页面刷新把输入框重建为空……）都会把用户已配好的 Key 抹掉。
   * 症状还是**重启后**才连不上，排查成本极高。把删除收窄成显式动作后，
   * 这一类事故在结构上就不可能再发生 —— 这是最后一道防线，
   * 即使前端又写错了也不会丢密钥。
   *
   * 渲染层只掌握"用户刚编辑过"的那几个值，全量替换会把其余 Key 一起抹掉，
   * 所以写入一律走合并。
   */
  merge(patch: SecretsPatch): SecretsStatus {
    const current = this.load()
    const next: SecretsPayload = {
      models: { ...current.models },
      mcp: Object.fromEntries(Object.entries(current.mcp).map(([k, v]) => [k, { ...v }])),
      integrations: Object.fromEntries(
        Object.entries(current.integrations ?? {}).map(([k, v]) => [k, { ...v }]),
      ),
    }

    for (const [id, key] of Object.entries(patch.models ?? {})) {
      // 空值 = 未提供（不是删除）。忽略掉，保住旧值。
      if (key) next.models[id] = key
    }
    for (const id of patch.removeModelIds ?? []) {
      delete next.models[id]
    }

    for (const [server, env] of Object.entries(patch.mcp ?? {})) {
      const target = { ...(next.mcp[server] ?? {}) }
      for (const [name, value] of Object.entries(env ?? {})) {
        // 同样：空值忽略，保住旧值
        if (value) target[name] = value
      }
      if (Object.keys(target).length > 0) next.mcp[server] = target
      else delete next.mcp[server]
    }
    for (const [server, vars] of Object.entries(patch.removeMcpVars ?? {})) {
      const target = { ...(next.mcp[server] ?? {}) }
      for (const name of vars) delete target[name]
      if (Object.keys(target).length > 0) next.mcp[server] = target
      else delete next.mcp[server]
    }

    for (const [name, fields] of Object.entries(patch.integrations ?? {})) {
      const target = { ...(next.integrations[name] ?? {}) }
      for (const [key, value] of Object.entries(fields ?? {})) {
        // 与其它密钥一致的语义：空值忽略，保住旧值
        if (value) target[key] = value
      }
      if (Object.keys(target).length > 0) next.integrations[name] = target
      else delete next.integrations[name]
    }

    return this.save(next)
  }

  /**
   * 取**某一条**密钥的明文。这是全应用唯一会返回明文的地方，所以刻意做窄：
   *
   * - **一次只取一条**，没有"整份下发"的接口 —— 那正是"一次 XSS 打包外传
   *   所有 Key"的那条路；
   * - 只读不写，也不顺手缓存到别处；
   * - 取不到就返回空串，**不抛异常**：它只服务于"用户想看一眼"这个展示场景，
   *   为它中断设置页没有任何意义。
   *
   * 调用方（main.ts）会为每次取用记一条日志，界面上则是用户确认过才走到这里。
   */
  reveal(target: RevealTarget): string {
    const payload = this.load()
    if (target?.modelId) return payload.models[target.modelId] ?? ''
    if (target?.mcpServer && target?.mcpVar) {
      return payload.mcp[target.mcpServer]?.[target.mcpVar] ?? ''
    }
    if (target?.integration && target?.integrationField) {
      return payload.integrations[target.integration]?.[target.integrationField] ?? ''
    }
    return ''
  }

  /**
   * 给渲染层用的**脱敏预览**。
   *
   * 设置页的**常规**路径只需要这份预览：把"这个模型已配过 Key"显示出来，
   * 编辑走 merge 增量提交，没碰过的条目原样保留。
   *
   * 明文只在用户**明确要求查看**时按单条取（见上面的 reveal）。早先这里是
   * "一个下发明文的入口都不留"，但用户确实会需要核对"我粘进去的 Key 完不完整、
   * 有没有多带空格" —— 于是把它收窄成"按条 + 用户确认 + 记日志"，
   * 而不是完全不给。**全量下发仍然是禁止的。**
   */
  masked(): SecretsPayload {
    const payload = this.load()
    return {
      models: Object.fromEntries(
        Object.entries(payload.models).map(([id, key]) => [id, maskSecret(key)]),
      ),
      mcp: Object.fromEntries(
        Object.entries(payload.mcp).map(([server, env]) => [
          server,
          Object.fromEntries(
            Object.entries(env).map(([name, value]) => [name, maskSecret(value)]),
          ),
        ]),
      ),
      integrations: Object.fromEntries(
        Object.entries(payload.integrations ?? {}).map(([name, fields]) => [
          name,
          Object.fromEntries(
            Object.entries(fields).map(([key, value]) => [key, maskSecret(value)]),
          ),
        ]),
      ),
    }
  }

  status(): SecretsStatus {
    const payload = this.load()
    const count =
      Object.keys(payload.models).length +
      Object.values(payload.mcp).reduce((sum, env) => sum + Object.keys(env).length, 0) +
      Object.values(payload.integrations ?? {}).reduce(
        (sum, fields) => sum + Object.keys(fields).length,
        0,
      )
    return {
      available: safeStorage.isEncryptionAvailable(),
      protection: safeStorage.isEncryptionAvailable() ? 'encrypted' : 'plaintext',
      path: this.filePath,
      count,
    }
  }

  // ------------------------------------------------------------------ //
  // 一次性交接给 Python
  // ------------------------------------------------------------------ //
  /**
   * 把密钥写成临时文件，返回其路径（供 `AGENT_SECRETS_FILE` 环境变量使用）。
   *
   * 即使密钥为空也要写：**路径的存在本身就是信号**，告诉 Python 侧
   * "密钥由外部托管，保存配置时请剥离密钥字段"。少了这个信号，
   * 开发模式（没有 safeStorage）下用户填的 Key 会在下次保存时被写进明文配置。
   */
  materialize(): string {
    const target = path.join(
      os.tmpdir(),
      `agent-secrets-${crypto.randomBytes(12).toString('hex')}.json`,
    )
    fs.writeFileSync(target, JSON.stringify(this.load()), { encoding: 'utf-8', mode: 0o600 })
    this.tempFile = target
    return target
  }

  /** 清理交接用的临时文件。核心进程读完会自己删，这里只是失败兜底。 */
  cleanupTempFile(): void {
    if (!this.tempFile) return
    try {
      fs.rmSync(this.tempFile, { force: true })
    } catch {
      // 已被核心删掉是正常情况
    }
    this.tempFile = null
  }

  // ------------------------------------------------------------------ //
  // 旧版明文配置迁移
  // ------------------------------------------------------------------ //
  /**
   * 把历史上明文写在 `config/*.json` 里的密钥搬进加密存储，并从配置文件抹掉。
   *
   * 必须在拉起后端**之前**执行，且只做一次：之后配置文件里的密钥字段永远是空的，
   * 这个方法再跑也找不到东西可搬。
   */
  migrateFromConfigFiles(configDir: string): number {
    let moved = 0
    const payload = this.load()
    let dirty = false

    const modelsFile = path.join(configDir, 'models.json')
    try {
      if (fs.existsSync(modelsFile)) {
        const raw = JSON.parse(fs.readFileSync(modelsFile, 'utf-8')) as {
          models?: Array<Record<string, unknown>>
        }
        for (const spec of raw.models ?? []) {
          const id = typeof spec.id === 'string' ? spec.id : ''
          const key = typeof spec.api_key === 'string' ? spec.api_key : ''
          if (id && key && !payload.models[id]) {
            payload.models[id] = key
            moved += 1
          }
          spec.api_key = ''
        }
        fs.writeFileSync(modelsFile, JSON.stringify(raw, null, 2), 'utf-8')
      }
    } catch (error) {
      console.error('[secrets] 迁移 models.json 失败:', error)
    }

    const mcpFile = path.join(configDir, 'mcp.json')
    try {
      if (fs.existsSync(mcpFile)) {
        const raw = JSON.parse(fs.readFileSync(mcpFile, 'utf-8')) as {
          servers?: Array<Record<string, unknown>>
        }
        for (const server of raw.servers ?? []) {
          const name = typeof server.name === 'string' ? server.name : ''
          const env = (server.env ?? {}) as Record<string, string>
          if (!name || typeof env !== 'object') continue
          const kept: Record<string, string> = {}
          for (const [key, value] of Object.entries(env)) {
            if (SECRET_KEY_HINT.test(key) && value) {
              payload.mcp[name] = { ...(payload.mcp[name] ?? {}), [key]: value }
              moved += 1
            } else {
              kept[key] = value
            }
          }
          server.env = kept
        }
        fs.writeFileSync(mcpFile, JSON.stringify(raw, null, 2), 'utf-8')
      }
    } catch (error) {
      console.error('[secrets] 迁移 mcp.json 失败:', error)
    }

    if (moved > 0) {
      dirty = true
      console.log(`[secrets] 已把 ${moved} 条明文密钥迁移进加密存储`)
    }
    if (dirty) {
      this.save(payload)
    }
    return moved
  }
}
