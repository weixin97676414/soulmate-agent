























import fs from 'node:fs'
import path from 'node:path'

import { app } from 'electron'

const LOG_DIR = 'logs'
const LOG_NAME = 'desktop.log'

const MAX_BYTES = 1024 * 1024

let dirReady = false

function logDir(): string {
  return path.join(app.getPath('userData'), LOG_DIR)
}

function logPath(): string {
  return path.join(logDir(), LOG_NAME)
}

function ensureDir(): boolean {
  if (dirReady) return true
  try {
    fs.mkdirSync(logDir(), { recursive: true })
    dirReady = true
    return true
  } catch {
    return false
  }
}

function rotateIfNeeded(file: string): void {
  let size = 0
  try {
    size = fs.statSync(file).size
  } catch {
    return 
  }
  if (size < MAX_BYTES) return
  try {
    
    
    fs.renameSync(file, `${file}.1`)
  } catch {
    
  }
}







export function logDesktop(message: string): void {
  const line = `${new Date().toISOString()} ${message}\n`
  
  console.log(`[desktop] ${message}`)

  if (!ensureDir()) return
  const file = logPath()
  rotateIfNeeded(file)
  try {
    fs.appendFileSync(file, line, 'utf-8')
  } catch {
    
  }
}
