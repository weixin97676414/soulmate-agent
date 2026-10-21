



















import net from 'node:net'
import tls from 'node:tls'

import { app } from 'electron'

import type { AccountLine, AccountLineState } from '../../shared/bridge'
import { API_PREFIX, baseFor } from './api'


const PROBE_TIMEOUT_MS = 2_000

export const FULL_ROUNDS = 5

export const QUICK_ROUNDS = 2

const TIE_MS = 20
const TIE_RATIO = 0.15

const SWITCH_RATIO = 0.3

const STALE_MS = 24 * 60 * 60 * 1000

export const ACCOUNT_LINES: readonly AccountLine[] = ['cn', 'seoul']







export function probeOnce(base: string, timeoutMs = PROBE_TIMEOUT_MS): Promise<number> {
  const url = new URL(base + API_PREFIX + '/ping')
  const secure = url.protocol === 'https:'
  const port = url.port ? Number(url.port) : secure ? 443 : 80
  const request =
    `GET ${url.pathname} HTTP/1.1\r\nHost: ${url.host}\r\n` +
    'User-Agent: soulmate-desktop\r\nConnection: close\r\n\r\n'

  return new Promise((resolve, reject) => {
    const started = performance.now()
    let settled = false
    let timer: NodeJS.Timeout | null = null

    const socket = secure
      ? tls.connect({ host: url.hostname, port, servername: url.hostname })
      : net.connect({ host: url.hostname, port })

    const finish = (error?: Error): void => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      socket.destroy()
      if (error) reject(error)
      else resolve(performance.now() - started)
    }

    timer = setTimeout(() => finish(new Error('探测超时')), timeoutMs)
    socket.once(secure ? 'secureConnect' : 'connect', () => socket.write(request))
    socket.once('error', (error: Error) => finish(error))
    
    socket.on('data', () => finish())
  })
}

function median(values: number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  if (sorted.length % 2 === 1) return Math.round(sorted[middle])
  return Math.round((sorted[middle - 1] + sorted[middle]) / 2)
}

export interface LineMeasurements {
  measurements: Record<string, number | null>
  
  samples: Record<string, number[]>
}


export async function measureLines(rounds = FULL_ROUNDS): Promise<LineMeasurements> {
  const attempts: Record<string, (number | null)[]> = { cn: [], seoul: [] }
  for (let round = 0; round < rounds; round += 1) {
    
    const order = round % 2 === 0 ? ACCOUNT_LINES : [...ACCOUNT_LINES].reverse()
    for (const line of order) {
      try {
        attempts[line].push(await probeOnce(baseFor(line)))
      } catch {
        attempts[line].push(null)
      }
    }
  }

  const measurements: Record<string, number | null> = {}
  const samples: Record<string, number[]> = {}
  for (const line of ACCOUNT_LINES) {
    const kept = attempts[line].slice(1).filter((value): value is number => value !== null)
    samples[line] = kept
    measurements[line] = median(kept)
  }
  return { measurements, samples }
}


function defaultByLocale(): AccountLine {
  return app.getLocale().toLowerCase().replace('_', '-').startsWith('zh') ? 'cn' : 'seoul'
}


function isComparable(a: number, b: number): boolean {
  const gap = Math.abs(a - b)
  return gap < TIE_MS || gap / Math.max(a, b) < TIE_RATIO
}

export function isStale(state: AccountLineState | null): boolean {
  if (!state) return true
  return Date.now() - state.updatedAt > STALE_MS
}







export function decideLine(
  measured: LineMeasurements,
  previous: AccountLineState | null,
): AccountLineState | null {
  const cn = measured.measurements.cn
  const seoul = measured.measurements.seoul
  if (cn === null && seoul === null) return null

  const updatedAt = Date.now()
  const manual = previous?.manual ?? false

  
  if (cn === null || seoul === null) {
    return {
      preferred: cn === null ? 'seoul' : 'cn',
      measurements: measured.measurements,
      updatedAt,
      manual,
    }
  }

  
  
  const better: AccountLine = cn <= seoul ? 'cn' : 'seoul'
  const fastMs = Math.min(cn, seoul)
  const slowMs = Math.max(cn, seoul)
  const comparable = isComparable(cn, seoul)

  
  if (manual && previous && measured.measurements[previous.preferred] !== null) {
    return { preferred: previous.preferred, measurements: measured.measurements, updatedAt, manual }
  }

  
  if (!previous) {
    return {
      preferred: comparable ? defaultByLocale() : better,
      measurements: measured.measurements,
      updatedAt,
      manual,
    }
  }

  
  
  
  const advantage = (slowMs - fastMs) / Math.max(slowMs, 1)
  const preferred: AccountLine =
    better !== previous.preferred && advantage > SWITCH_RATIO ? better : previous.preferred

  return { preferred, measurements: measured.measurements, updatedAt, manual }
}
