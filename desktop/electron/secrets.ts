




















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


const SECRET_KEY_HINT = /key|token|secret|password|passwd|credential|auth/i

export function emptySecrets(): SecretsPayload {
  return { models: {}, mcp: {}, integrations: {} }
}













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

  
  
  
  load(): SecretsPayload {
    if (this.cached) return this.cached
    
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
      
      if (key) next.models[id] = key
    }
    for (const id of patch.removeModelIds ?? []) {
      delete next.models[id]
    }

    for (const [server, env] of Object.entries(patch.mcp ?? {})) {
      const target = { ...(next.mcp[server] ?? {}) }
      for (const [name, value] of Object.entries(env ?? {})) {
        
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
        
        if (value) target[key] = value
      }
      if (Object.keys(target).length > 0) next.integrations[name] = target
      else delete next.integrations[name]
    }

    return this.save(next)
  }

  










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

  
  
  
  






  materialize(): string {
    const target = path.join(
      os.tmpdir(),
      `agent-secrets-${crypto.randomBytes(12).toString('hex')}.json`,
    )
    fs.writeFileSync(target, JSON.stringify(this.load()), { encoding: 'utf-8', mode: 0o600 })
    this.tempFile = target
    return target
  }

  
  cleanupTempFile(): void {
    if (!this.tempFile) return
    try {
      fs.rmSync(this.tempFile, { force: true })
    } catch {
      
    }
    this.tempFile = null
  }

  
  
  
  





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
