/**
 * **用户给技能的密钥**的加密存储（私钥 / API Secret 之类）。
 *
 * ## ⚠️ 它与 `secrets.ts` 是两条**互不相干**的链路，别合并
 *
 * | | `secrets.ts` | 本文件 |
 * |---|---|---|
 * | 存什么 | 模型 API Key / MCP 环境变量 / 集成凭据 | 用户经 `request_secret` 交给技能的东西 |
 * | 结构 | 固定三段式 `{models, mcp, integrations}` | 扁平 `名字 -> 值` |
 * | 文件 | `secrets.bin` | `skill-secrets.bin` |
 * | 注入变量 | `AGENT_SECRETS_FILE` | `AGENT_SKILL_SECRETS_FILE` |
 *
 * 产品要求："不要动我们现有的秘钥存储逻辑"。
 * 而且**技术上也不该合**：`secrets.ts` 的 `normalize()` 只保留那三个顶层键，
 * 其余键会被**静默丢弃** —— 往里塞第四种东西的后果是"存进去就没了、且不报错"，
 * 属于最难查的那类问题。
 *
 * ## 加解密**与 `secrets.ts` 共用同一份实现**
 *
 * 不是"各写一份、内容碰巧一样"，而是**同一个模块**：
 * `safeStorage.encryptString()`（Windows 即 DPAPI，绑定当前用户）、
 * 封套 `{v, encrypted, data}`、先写 `.tmp` 再 rename、不支持加密时明文降级并告警、
 * 解密失败**不删文件**（删了就永久丢数据）、以及脱敏预览的格式与阈值 ——
 * 全在 `secret-envelope.ts`。
 * 这几条任何一条走样，表现都是"用户重启后密钥没了"，而且没有任何报错。
 * （第 86 批 B 组收拢前，这里与 `secrets.ts` 是逐字复制的两份，**已经漂移**：
 * 脱敏阈值一个 `<= 10` 一个 `<= 8`，而 Python 侧用的是 `<= 8`。）
 */
import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { app, safeStorage } from 'electron'

import type { SkillSecretsPatch, SkillSecretsView } from '../shared/bridge'
import { maskSecret, readSecretFile, writeSecretFile } from './secret-envelope'

const SECRETS_FILE = 'skill-secrets.bin'

/** 名字的合法字符集 —— 与核心 `security/secret_ref.py::SECRET_NAME_PATTERN` 同一套。 */
const NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/

export class SkillSecretsStore {
  private cached: Record<string, string> | null = null
  private tempFile: string | null = null

  private file(): string {
    return path.join(app.getPath('userData'), SECRETS_FILE)
  }

  // ------------------------------------------------------------------ //
  // 读写
  // ------------------------------------------------------------------ //
  load(): Record<string, string> {
    if (this.cached) return this.cached
    // 文件不存在是**常态**（用户还没提供过任何密钥）；损坏 / 换机器导致 DPAPI
    // 解不开也一律降级成空，**绝不删文件**（理由见 `readSecretFile`）。
    // ⚠️ 与以前不同的一点：损坏 / 解密失败现在会**打一条日志**（以前什么都没有）。
    // "静默降级"是这个项目最不能接受的失败方式 —— 密钥文件损坏必须留痕。
    const raw = readSecretFile(this.file(), 'skill-secrets')
    this.cached = raw === null ? {} : normalize(raw)
    return this.cached
  }

  private persist(payload: Record<string, string>): void {
    writeSecretFile(this.file(), payload, 'skill-secrets')
  }

  /**
   * 合并写入（**空值忽略、绝不删除**）。
   *
   * 删除必须走显式的 `remove()` —— 与 `secrets.ts` 同一条口径：
   * 渲染层提交时往往只带"用户刚编辑的那几个",把空串当删除会让其余项被一起抹掉。
   */
  mergeSave(patch: SkillSecretsPatch): SkillSecretsView {
    const next = { ...this.load() }
    for (const [name, value] of Object.entries(patch.keys ?? {})) {
      const trimmed = String(value ?? '')
      // 名字非法 / 值为空 → 忽略。**不报错**：用户可能只是把一个字段留空了，
      // 那不是错误，只是没填。真正的错误（名字不合法）由渲染层先拦一道。
      if (!NAME_PATTERN.test(name) || !trimmed) continue
      next[name] = trimmed
    }
    this.cached = next
    this.persist(next)
    return this.view()
  }

  /** 显式删除（单条或全部）。这是**唯一**会让条目消失的入口。 */
  remove(names: string[] | null): SkillSecretsView {
    const next = { ...this.load() }
    if (names && names.length > 0) {
      for (const name of names) delete next[name]
    } else {
      for (const key of Object.keys(next)) delete next[key]
    }
    this.cached = next
    this.persist(next)
    return this.view()
  }

  /**
   * 给界面看的视图：**名字 + 脱敏值**，永远不下发明文。
   *
   * ⚠️ 不下发明文是刻意的，也是这套设计的一部分：应用里**没有任何界面**
   * 能显示出用户给技能的密钥内容。要换一把就重新提供（覆盖同名即可）——
   * "能看"和"能被偷看"是同一件事。
   */
  view(): SkillSecretsView {
    const payload = this.load()
    const names = Object.keys(payload).sort()
    return {
      names,
      masked: Object.fromEntries(names.map((name) => [name, maskSecret(payload[name])])),
      available: safeStorage.isEncryptionAvailable(),
      protection: safeStorage.isEncryptionAvailable() ? 'encrypted' : 'plaintext',
      path: this.file(),
    }
  }

  /**
   * 把全部密钥写进一个临时文件，返回路径给核心读（`AGENT_SKILL_SECRETS_FILE`）。
   *
   * ⚠️ 与 `secrets.ts` 的 `materialize()` **同一个理由**：不用环境变量直接传值，
   * 因为环境变量会被子进程继承，而核心进程会 spawn MCP Server —— 密钥会直接漏给
   * 第三方进程。传路径则"核心读完立即删除，且只有它知道路径"。
   *
   * ⚠️ 空也要写：文件存在 = "密钥由外部托管"的信号。少了它，核心会以为
   * "没人管密钥"，语义就变了（对照 `config/secrets.py` 的 `read_secrets_file`）。
   */
  materialize(): string {
    const target = path.join(
      os.tmpdir(),
      `agent-skill-secrets-${crypto.randomBytes(12).toString('hex')}.json`,
    )
    fs.writeFileSync(target, JSON.stringify({ keys: this.load() }), 'utf-8')
    this.tempFile = target
    return target
  }

  /** 清理交接用的临时文件。核心读完会自己删，这里只是失败兜底。 */
  cleanupTempFile(): void {
    if (!this.tempFile) return
    try {
      fs.rmSync(this.tempFile, { force: true })
    } catch {
      // 兜底清理失败不该影响任何功能
    }
    this.tempFile = null
  }
}

/** 把外部内容收敛成扁平 `名字 -> 值`，脏数据一律忽略。 */
function normalize(raw: unknown): Record<string, string> {
  const source =
    raw && typeof raw === 'object' && 'keys' in (raw as Record<string, unknown>)
      ? (raw as { keys?: unknown }).keys
      : raw
  if (!source || typeof source !== 'object') return {}
  const result: Record<string, string> = {}
  for (const [name, value] of Object.entries(source as Record<string, unknown>)) {
    if (!NAME_PATTERN.test(name)) continue
    if (typeof value !== 'string' || !value) continue
    result[name] = value
  }
  return result
}
