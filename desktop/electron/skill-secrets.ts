



























import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { app, safeStorage } from 'electron'

import type { SkillSecretsPatch, SkillSecretsView } from '../shared/bridge'
import { maskSecret, readSecretFile, writeSecretFile } from './secret-envelope'

const SECRETS_FILE = 'skill-secrets.bin'


const NAME_PATTERN = /^[A-Za-z0-9_-]{1,64}$/

export class SkillSecretsStore {
  private cached: Record<string, string> | null = null
  private tempFile: string | null = null

  private file(): string {
    return path.join(app.getPath('userData'), SECRETS_FILE)
  }

  
  
  
  load(): Record<string, string> {
    if (this.cached) return this.cached
    
    
    
    
    const raw = readSecretFile(this.file(), 'skill-secrets')
    this.cached = raw === null ? {} : normalize(raw)
    return this.cached
  }

  private persist(payload: Record<string, string>): void {
    writeSecretFile(this.file(), payload, 'skill-secrets')
  }

  





  mergeSave(patch: SkillSecretsPatch): SkillSecretsView {
    const next = { ...this.load() }
    for (const [name, value] of Object.entries(patch.keys ?? {})) {
      const trimmed = String(value ?? '')
      
      
      if (!NAME_PATTERN.test(name) || !trimmed) continue
      next[name] = trimmed
    }
    this.cached = next
    this.persist(next)
    return this.view()
  }

  
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

  









  materialize(): string {
    const target = path.join(
      os.tmpdir(),
      `agent-skill-secrets-${crypto.randomBytes(12).toString('hex')}.json`,
    )
    fs.writeFileSync(target, JSON.stringify({ keys: this.load() }), 'utf-8')
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
}


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
