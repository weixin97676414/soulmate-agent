



































import crypto from 'node:crypto'
import fs from 'node:fs'
import { createWriteStream } from 'node:fs'
import path from 'node:path'
import { Readable } from 'node:stream'
import { pipeline } from 'node:stream/promises'

import { app, net, shell } from 'electron'

import type { UpdateState } from '../shared/bridge'
import { logDesktop } from './desktop-log'


const FIRST_DELAY_MS = 10_000
const INTERVAL_MS = 60 * 60 * 1000


const REQUEST_TIMEOUT_MS = 30_000


const CONCURRENCY = 3









const isMac = process.platform === 'darwin'
const LINES = {
  cn: {
    baseUrl: 'https://china.xinjianxue.com/updates',
    fullPackage: isMac
      ? 'https://china.xinjianxue.com/download/mac/Soulmate-Agent-1.0.2.dmg'
      : 'https://china.xinjianxue.com/download/win/Soulmate-Agent-Setup-1.0.2.exe',
  },
  seoul: {
    baseUrl: 'https://raw.githubusercontent.com/weixin97676414/soulmate-agent/main/updates',
    fullPackage: isMac
      ? 'https://github.com/weixin97676414/soulmate-agent/releases/download/v1.0.2/Soulmate-Agent-1.0.2.dmg'
      : 'https://github.com/weixin97676414/soulmate-agent/releases/download/v1.0.2/Soulmate-Agent-Setup-1.0.2.exe',
  },
} as const

type Line = keyof typeof LINES








function scopeDirs(): Record<string, string> {
  
  const resources = process.resourcesPath
  return {
    renderer: path.join(resources, 'dist'),
    core: path.join(resources, 'agent-core', '_internal', 'my_agent'),
  }
}


interface ManifestFile {
  target: string
  path: string
  size: number
  sha256: string
}

interface Manifest {
  version: string
  min_from: string
  line: string
  generated_at: string
  
  full_package?: string
  files: ManifestFile[]
}


interface Persisted {
  
  appliedVersion: string
  
  pending: { manifest: Manifest; line: Line } | null
  
  fingerprints: Record<string, { size: number; mtime: number; sha256: string }>
  lastCheckedAt: string
}

const EMPTY: Persisted = { appliedVersion: '', pending: null, fingerprints: {}, lastCheckedAt: '' }

let persisted: Persisted = { ...EMPTY }
let state: UpdateState = {
  supported: false,
  phase: 'idle',
  version: app.getVersion(),
  availableVersion: null,
  total: 0,
  downloaded: 0,
  bytesDone: 0,
  bytesTotal: 0,
  pendingApply: false,
  fullPackageUrl: '',
  lastCheckedAt: '',
  message: '尚未检查',
}


let persistedLoaded = false
let line: Line = 'cn'







let latestFullPackage: string | null = null
let listeners: Array<(s: UpdateState) => void> = []
let timer: NodeJS.Timeout | null = null
let checking = false



const stateFile = (): string => path.join(app.getPath('userData'), 'update-state.json')
const stagingDir = (): string => path.join(app.getPath('userData'), 'update-staging')
const backupDir = (): string => path.join(app.getPath('userData'), 'update-backup')

function log(message: string): void {
  logDesktop(`[update] ${message}`)
}


function patch(next: Partial<UpdateState>): void {
  state = { ...state, ...next }
  for (const fn of listeners) {
    try {
      fn(state)
    } catch {
      
    }
  }
}

function loadPersisted(): void {
  try {
    const raw = JSON.parse(fs.readFileSync(stateFile(), 'utf8')) as Partial<Persisted>
    persisted = {
      appliedVersion: typeof raw.appliedVersion === 'string' ? raw.appliedVersion : '',
      pending: raw.pending && typeof raw.pending === 'object' ? (raw.pending as Persisted['pending']) : null,
      fingerprints: raw.fingerprints && typeof raw.fingerprints === 'object' ? raw.fingerprints : {},
      lastCheckedAt: typeof raw.lastCheckedAt === 'string' ? raw.lastCheckedAt : '',
    }
  } catch {
    
    persisted = { ...EMPTY }
  }
  persistedLoaded = true
}

function savePersisted(): void {
  try {
    fs.writeFileSync(stateFile(), JSON.stringify(persisted), 'utf8')
  } catch (error) {
    log(`状态落盘失败：${String(error)}`)
  }
}









function currentVersion(): string {
  const applied = persisted.appliedVersion
  const installed = app.getVersion()
  if (applied && compareVersion(applied, installed) > 0) return applied
  return installed
}

function setLine(next: string): void {
  if (next === 'cn' || next === 'seoul') line = next
}


function fullPackageUrl(): string {
  return latestFullPackage || LINES[line].fullPackage
}

function fileSha256(file: string): string {
  const hash = crypto.createHash('sha256')
  hash.update(fs.readFileSync(file))
  return hash.digest('hex')
}


function cachedSha(target: string, rel: string, full: string): string | null {
  let stat: fs.Stats
  try {
    stat = fs.statSync(full)
  } catch {
    return null 
  }
  const key = `${target}|${rel}`
  const hit = persisted.fingerprints[key]
  if (hit && hit.size === stat.size && hit.mtime === stat.mtimeMs) return hit.sha256
  try {
    const sha = fileSha256(full)
    persisted.fingerprints[key] = { size: stat.size, mtime: stat.mtimeMs, sha256: sha }
    return sha
  } catch {
    return null
  }
}



async function fetchJson<T>(url: string): Promise<T> {
  
  
  
  
  
  const sep = url.includes('?') ? '&' : '?'
  const response = await net.fetch(`${url}${sep}_=${Date.now()}`, {
    
    credentials: 'omit',
    redirect: 'follow', 
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    headers: { accept: 'application/json' },
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  return (await response.json()) as T
}

async function downloadTo(url: string, file: string): Promise<void> {
  const response = await net.fetch(url, {
    credentials: 'omit',
    redirect: 'follow',
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}`)
  if (!response.body) throw new Error('响应没有 body')

  fs.mkdirSync(path.dirname(file), { recursive: true })
  
  const part = `${file}.part`
  await pipeline(Readable.fromWeb(response.body as never), createWriteStream(part))
  fs.renameSync(part, file)
}




function planDownloads(manifest: Manifest): { need: Map<string, number>; stale: ManifestFile[] } {
  const dirs = scopeDirs()
  const need = new Map<string, number>() 
  const stale: ManifestFile[] = []

  for (const item of manifest.files) {
    if (!dirs[item.target]) continue 
    const full = path.join(dirs[item.target], item.path)
    const local = cachedSha(item.target, item.path, full)
    if (local === item.sha256) continue
    stale.push(item)
    need.set(item.sha256, item.size)
  }
  return { need, stale }
}

async function runCheck(auto: boolean): Promise<void> {
  if (checking) return
  if (!state.supported) {
    if (!auto) patch({ message: state.message })
    return
  }
  checking = true
  patch({ phase: 'checking', message: '正在检查更新…' })

  try {
    const base = LINES[line].baseUrl
    const manifest = await fetchJson<Manifest>(`${base}/manifest-${line}.json`)
    persisted.lastCheckedAt = new Date().toISOString()
    
    if (typeof manifest?.full_package === 'string' && manifest.full_package.trim()) {
      latestFullPackage = manifest.full_package.trim()
    }
    patch({ lastCheckedAt: persisted.lastCheckedAt, fullPackageUrl: fullPackageUrl() })

    if (!manifest || !Array.isArray(manifest.files)) throw new Error('清单格式不对')

    const mine = currentVersion()
    if (manifest.version === mine && !persisted.pending) {
      patch({ phase: 'idle', availableVersion: null, total: 0, downloaded: 0, message: `已是最新（${mine}）` })
      log(`清单版本 ${manifest.version} 与本地一致，无需更新`)
      return
    }

    
    
    
    if (isDowngrade(manifest.version, mine)) {
      dropStalePending() 
      patch({
        phase: 'idle',
        availableVersion: null,
        total: 0,
        downloaded: 0,
        message: `服务器版本（${manifest.version}）比本机（${mine}）旧，已跳过更新`,
      })
      log(`清单 ${manifest.version} < 本地 ${mine} ⇒ 拒绝降级`)
      return
    }

    
    
    if (process.platform === 'darwin') {
      patch({
        phase: 'need-full',
        availableVersion: manifest.version,
        message: `发现新版本 ${manifest.version}，请下载完整安装包`,
      })
      log(`mac 检测到新版本 ${manifest.version}，走整包替换（不做文件级增量）`)
      return
    }

    
    if (compareVersion(mine, manifest.min_from) < 0) {
      patch({
        phase: 'need-full',
        availableVersion: manifest.version,
        message: `当前版本 ${mine} 无法增量更新，需要下载完整安装包`,
      })
      log(`本地 ${mine} < min_from ${manifest.min_from} ⇒ 需要整包重装`)
      return
    }

    const { need, stale } = planDownloads(manifest)
    if (need.size === 0) {
      
      persisted.appliedVersion = manifest.version
      savePersisted()
      patch({ phase: 'idle', version: manifest.version, availableVersion: null, message: `已是最新（${manifest.version}）` })
      return
    }

    const bytesTotal = [...need.values()].reduce((sum, n) => sum + n, 0)
    patch({
      phase: 'downloading',
      availableVersion: manifest.version,
      total: need.size,
      downloaded: 0,
      bytesDone: 0,
      bytesTotal,
      message: `发现新版本 ${manifest.version}，正在下载 ${need.size} 个文件`,
    })
    log(`目标 ${manifest.version}：${stale.length} 条路径不一致，去重后需下载 ${need.size} 个（${bytesTotal} 字节）`)

    fs.rmSync(stagingDir(), { recursive: true, force: true })
    fs.mkdirSync(stagingDir(), { recursive: true })

    const tasks = [...need.entries()]
    let done = 0
    let bytesDone = 0
    let cursor = 0

    const worker = async (): Promise<void> => {
      for (;;) {
        const index = cursor
        cursor += 1
        const task = tasks[index]
        if (!task) return
        const [sha, size] = task
        const target = path.join(stagingDir(), sha.slice(0, 2), `${sha}.bin`)
        if (!fs.existsSync(target)) {
          await downloadTo(`${base}/files/${sha.slice(0, 2)}/${sha}.bin`, target)
        }
        
        const actual = fileSha256(target)
        if (actual !== sha) {
          fs.rmSync(target, { force: true })
          throw new Error(`校验不符（期望 ${sha.slice(0, 8)}，实际 ${actual.slice(0, 8)}）`)
        }
        done += 1
        bytesDone += size
        patch({ downloaded: done, bytesDone })
      }
    }

    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, tasks.length) }, worker))

    persisted.pending = { manifest, line }
    savePersisted()
    patch({
      phase: 'ready',
      pendingApply: true,
      downloaded: need.size,
      message: `新版本 ${manifest.version} 已下载，重启后生效`,
    })
    log(`下载校验全部通过 ⇒ 待应用 ${manifest.version}`)
  } catch (error) {
    
    const why = error instanceof Error ? error.message : String(error)
    log(`检查/下载失败：${why}`)
    patch({
      phase: 'error',
      message: auto ? `检查更新失败（${why}）` : `检查更新失败：${why}`,
    })
  } finally {
    checking = false
  }
}


export function compareVersion(a: string, b: string): number {
  const parse = (v: string): number[] | null => {
    const m = /^(\d+)\.(\d+)\.(\d+)$/.exec(v.trim())
    return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null
  }
  const pa = parse(a)
  const pb = parse(b)
  if (!pa || !pb) return 0
  for (let i = 0; i < 3; i += 1) {
    if (pa[i] !== pb[i]) return pa[i] < pb[i] ? -1 : 1
  }
  return 0
}










export function applyPendingAtBoot(): void {
  
  
  
  if (!persistedLoaded) loadPersisted()
  dropStalePending() 
  const pending = persisted.pending
  if (!pending) return
  const dirs = scopeDirs()

  
  
  
  
  const plan: Array<{ item: ManifestFile; full: string; staged: string }> = []
  for (const item of pending.manifest.files) {
    const dir = dirs[item.target]
    if (!dir) continue
    const full = path.join(dir, item.path)
    
    if (fs.existsSync(full) && fileSha256(full) === item.sha256) continue
    const staged = path.join(stagingDir(), item.sha256.slice(0, 2), `${item.sha256}.bin`)
    if (!fs.existsSync(staged)) {
      log(`暂存区缺 ${item.target}/${item.path}，本次不应用（保留待应用标记，下次重试）`)
      patch({ phase: 'error', pendingApply: true, message: '更新文件不完整，将在下次启动重试' })
      return
    }
    if (fileSha256(staged) !== item.sha256) {
      log(`暂存区 ${item.target}/${item.path} 校验不符，丢弃待应用更新`)
      persisted.pending = null
      savePersisted()
      try {
        fs.rmSync(stagingDir(), { recursive: true, force: true })
      } catch {
        
      }
      patch({ phase: 'error', pendingApply: false, message: '更新文件已损坏，已清除，请重新检查更新' })
      return
    }
    plan.push({ item, full, staged })
  }

  
  if (plan.length === 0) {
    persisted.appliedVersion = pending.manifest.version
    persisted.pending = null
    savePersisted()
    try {
      fs.rmSync(stagingDir(), { recursive: true, force: true })
    } catch {
      
    }
    patch({ phase: 'idle', version: pending.manifest.version, pendingApply: false, downloaded: 0, total: 0, message: `已更新到 ${pending.manifest.version}` })
    log(`本地已是 ${pending.manifest.version}，无需替换`)
    return
  }

  
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const backup = path.join(backupDir(), stamp)
  const replaced: Array<{ full: string; backup: string | null }> = []

  try {
    for (const { item, full, staged } of plan) {
      fs.mkdirSync(path.dirname(full), { recursive: true })
      let old: string | null = null
      if (fs.existsSync(full)) {
        old = path.join(backup, item.target, item.path)
        fs.mkdirSync(path.dirname(old), { recursive: true })
        fs.renameSync(full, old)
      }
      const tmp = `${full}.new-${process.pid}`
      fs.copyFileSync(staged, tmp)
      fs.renameSync(tmp, full)
      replaced.push({ full, backup: old })
    }

    persisted.appliedVersion = pending.manifest.version
    persisted.pending = null
    savePersisted()
    try {
      fs.rmSync(stagingDir(), { recursive: true, force: true })
    } catch {
      
    }
    pruneBackups(backup)
    patch({ phase: 'idle', version: pending.manifest.version, pendingApply: false, downloaded: 0, total: 0, message: `已更新到 ${pending.manifest.version}` })
    log(`已应用 ${pending.manifest.version}（替换 ${replaced.length} 个文件，备份在 ${backup}）`)
  } catch (error) {
    const why = error instanceof Error ? error.message : String(error)
    log(`应用失败，开始回滚：${why}`)
    for (const item of replaced.reverse()) {
      try {
        if (item.backup) {
          fs.renameSync(item.backup, item.full)
        } else {
          fs.rmSync(item.full, { force: true })
        }
      } catch (rollbackError) {
        log(`回滚失败（${item.full}）：${String(rollbackError)}`)
      }
    }
    
    patch({ phase: 'error', message: `更新应用失败：${why}` })
  }
}







function pruneBackups(keepDir: string): void {
  const root = backupDir()
  try {
    for (const name of fs.readdirSync(root)) {
      const full = path.join(root, name)
      if (path.resolve(full) === path.resolve(keepDir)) continue
      try {
        fs.rmSync(full, { recursive: true, force: true })
      } catch {
        
      }
    }
  } catch {
    
  }
}


export function isDowngrade(remote: string, local: string): boolean {
  return compareVersion(remote, local) < 0
}









function dropStalePending(): void {
  const pending = persisted.pending
  if (!pending) return
  if (!isDowngrade(pending.manifest.version, currentVersion())) return
  log(`待应用版本 ${pending.manifest.version} 低于本机 ${currentVersion()} ⇒ 丢弃（拒绝降级）`)
  persisted.pending = null
  savePersisted()
  try {
    fs.rmSync(stagingDir(), { recursive: true, force: true })
  } catch {
    
  }
  patch({
    phase: 'idle',
    pendingApply: false,
    availableVersion: null,
    downloaded: 0,
    total: 0,
    message: `已忽略过期更新（${pending.manifest.version} 低于本机 ${currentVersion()}）`,
  })
}



export function initUpdater(options: { line?: string; autoUpdate: boolean }): void {
  setLine(options.line ?? 'cn')
  loadPersisted()
  dropStalePending() 

  
  const pendingManifest = persisted.pending?.manifest
  if (typeof pendingManifest?.full_package === 'string' && pendingManifest.full_package.trim()) {
    latestFullPackage = pendingManifest.full_package.trim()
  }

  const packaged = app.isPackaged
  const pending = persisted.pending !== null
  patch({
    supported: packaged,
    phase: packaged ? 'idle' : 'idle',
    version: currentVersion(),
    pendingApply: pending,
    fullPackageUrl: fullPackageUrl(),
    lastCheckedAt: persisted.lastCheckedAt,
    message: packaged
      ? pending
        ? '已下载更新，重启后生效'
        : '尚未检查'
      : '开发模式下不检查更新（发布版才有）',
  })

  setAutoUpdate(options.autoUpdate)
}







export function setAutoUpdate(enabled: boolean): void {
  if (timer) clearTimeout(timer)
  timer = null

  if (!app.isPackaged) {
    log('开发模式：跳过自动更新')
    return
  }
  if (!enabled) {
    log('用户已关闭自动检查更新（手动检查仍可用）')
    return
  }

  timer = setTimeout(() => {
    void runCheck(true)
    timer = setInterval(() => void runCheck(true), INTERVAL_MS)
  }, FIRST_DELAY_MS)
  
  timer.unref?.()
}




export function getUpdateState(): UpdateState {
  return { ...state, version: currentVersion(), fullPackageUrl: fullPackageUrl() }
}

export function onUpdateState(callback: (s: UpdateState) => void): () => void {
  listeners.push(callback)
  return () => {
    listeners = listeners.filter((fn) => fn !== callback)
  }
}

export async function checkForUpdate(): Promise<UpdateState> {
  await runCheck(false)
  return getUpdateState()
}

export async function applyUpdateNow(): Promise<UpdateState> {
  if (!persisted.pending) return getUpdateState()
  
  app.relaunch()
  app.exit(0)
  return getUpdateState()
}

export async function openFullPackage(): Promise<void> {
  const url = fullPackageUrl()
  log(`打开整包下载：${url}`)
  await shell.openExternal(url)
}


export function setUpdateLine(next: string): void {
  const before = line
  setLine(next)
  if (line !== before) {
    log(`线路切换 ${before} → ${line}`)
    if (app.isPackaged) void runCheck(true)
  }
}


export function __seedPendingForTest(manifest: Manifest): void {
  persisted.pending = { manifest, line: 'cn' }
  persistedLoaded = true
}


export function __setAppliedVersionForTest(version: string): void {
  persisted.appliedVersion = version
  persistedLoaded = true
}


export function __resetForTest(): void {
  persisted = { ...EMPTY }
  persistedLoaded = false
  checking = false
  latestFullPackage = null
  state = {
    supported: false,
    phase: 'idle',
    version: '0.0.0',
    availableVersion: null,
    total: 0,
    downloaded: 0,
    bytesDone: 0,
    bytesTotal: 0,
    pendingApply: false,
    fullPackageUrl: '',
    lastCheckedAt: '',
    message: '',
  }
}
