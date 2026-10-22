


























import fs from 'node:fs'
import path from 'node:path'

import { safeStorage } from 'electron'


export const SECRETS_FORMAT_VERSION = 1

export interface StoredEnvelope {
  v: number
  encrypted: boolean
  
  data: string
}










export function readSecretFile(filePath: string, label: string): unknown {
  let raw: string
  try {
    raw = fs.readFileSync(filePath, 'utf-8')
  } catch {
    
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
  
  fs.writeFileSync(tmp, JSON.stringify(envelope, null, 2), { encoding: 'utf-8', mode: 0o600 })
  fs.renameSync(tmp, filePath)
  return encrypted
}













export function maskSecret(value: string): string {
  if (!value) return ''
  
  if (value.length <= 8) return '*'.repeat(value.length)
  return `${value.slice(0, 4)}${'*'.repeat(6)}${value.slice(-4)}`
}
