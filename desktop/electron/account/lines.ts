/**
 * 线路探测与切换（文档 §6.3）。
 *
 * ## 为什么自己开 socket，而不是用 fetch 计时
 *
 * 文档要的指标是"TCP + TLS 握手 + 首字节耗时"。fetch 只能给"整个响应拿到手"的
 * 时间（还含服务端处理），两个域名的服务端负载一波动，结论就跟着抖 ——
 * 而线路结论是**粘性**的（写进本地、影响之后所有请求走哪边），不该被一次抖动带走。
 *
 * ## 两个刻意的稳定性处理
 *
 * - **丢弃第 1 次**：第一次要建 TLS 会话（冷启动），必然明显偏慢；
 * - **取中位数**而不是平均：单次被后台下载/杀毒扫描干扰时，中位数几乎不动。
 *
 * ## 手动选择要"粘"得住
 *
 * 用户手动选了首尔，每次启动的自动复测就不该把它抢回大陆。规则是：
 * 手动选过之后，**只有那一侧彻底连不上**才自动切走，并且会在界面上写明原因。
 * 否则"我明明选了首尔、它自己又跑回大陆了"会让人觉得这个开关是坏的。
 */
import net from 'node:net'
import tls from 'node:tls'

import { app } from 'electron'

import type { AccountLine, AccountLineState } from '../../shared/bridge'
import { API_PREFIX, baseFor } from './api'

/** 单次探测超时（文档 §6.3） */
const PROBE_TIMEOUT_MS = 2_000
/** 完整探测：每侧 5 次 */
export const FULL_ROUNDS = 5
/** 每次启动的快速复测：每侧 2 次 */
export const QUICK_ROUNDS = 2
/** 判"相当"：相差 < 20ms 或 < 15% */
const TIE_MS = 20
const TIE_RATIO = 0.15
/** 自动切换门槛：另一侧优势 > 30% */
const SWITCH_RATIO = 0.3
/** 结论的有效期：超过 24 小时重跑完整探测（文档 §6.4） */
const STALE_MS = 24 * 60 * 60 * 1000

export const ACCOUNT_LINES: readonly AccountLine[] = ['cn', 'seoul']

/**
 * 测一次：从 TCP 连接到**收到第一个字节**。
 *
 * https 走 `tls.connect`（会顺带做证书校验），http 走裸 TCP ——
 * 后者是给本地 mock 与联调用的，真机上两条线都是 https。
 */
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
    // 第一个字节到手即算完 —— 我们只要延迟，不需要响应内容
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
  /** 每一侧采到的样本（已丢弃第 1 次），给排查用 */
  samples: Record<string, number[]>
}

/** 两侧交替探测，并按文档丢弃每侧的第 1 次结果。 */
export async function measureLines(rounds = FULL_ROUNDS): Promise<LineMeasurements> {
  const attempts: Record<string, (number | null)[]> = { cn: [], seoul: [] }
  for (let round = 0; round < rounds; round += 1) {
    // 交替发：如果固定先测大陆，后测的那侧永远要多等一次对方
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

/** 系统语言属地在哪边（文档 §6.3：`zh-CN` → 大陆，否则首尔）。 */
function defaultByLocale(): AccountLine {
  return app.getLocale().toLowerCase().replace('_', '-').startsWith('zh') ? 'cn' : 'seoul'
}

/** 两个延迟是不是"相当" */
function isComparable(a: number, b: number): boolean {
  const gap = Math.abs(a - b)
  return gap < TIE_MS || gap / Math.max(a, b) < TIE_RATIO
}

export function isStale(state: AccountLineState | null): boolean {
  if (!state) return true
  return Date.now() - state.updatedAt > STALE_MS
}

/**
 * 根据测量结果得出结论。
 *
 * 两侧都不通时返回 null —— 那其实不是"线路问题"，而是**没联网**，
 * 由状态机去走离线分支（会弹一次「部分功能需要联网才能使用」）。
 */
export function decideLine(
  measured: LineMeasurements,
  previous: AccountLineState | null,
): AccountLineState | null {
  const cn = measured.measurements.cn
  const seoul = measured.measurements.seoul
  if (cn === null && seoul === null) return null

  const updatedAt = Date.now()
  const manual = previous?.manual ?? false

  // 一侧不通：直接用另一侧
  if (cn === null || seoul === null) {
    return {
      preferred: cn === null ? 'seoul' : 'cn',
      measurements: measured.measurements,
      updatedAt,
      manual,
    }
  }

  // 注意：`cn` / `seoul` 这里的类型是 number（上面已经把 null 分支返回掉了），
  // 下面算差值必须用它们，不能拿 `better`（那是 AccountLine，字符串）参与运算
  const better: AccountLine = cn <= seoul ? 'cn' : 'seoul'
  const fastMs = Math.min(cn, seoul)
  const slowMs = Math.max(cn, seoul)
  const comparable = isComparable(cn, seoul)

  // 手动选过：这一侧能连上就不动它（见模块说明）
  if (manual && previous && measured.measurements[previous.preferred] !== null) {
    return { preferred: previous.preferred, measurements: measured.measurements, updatedAt, manual }
  }

  // 没有旧结论：相当就按语言属地，否则挑快的
  if (!previous) {
    return {
      preferred: comparable ? defaultByLocale() : better,
      measurements: measured.measurements,
      updatedAt,
      manual,
    }
  }

  // 有旧结论：**另一侧优势超过 30% 才切**。
  // 切换本身不免费（新线路要重新握手、连接池全废），为 5% 的差距来回切会让
  // 每次启动都换一次出口，用户看到的延迟反而更抖。
  const advantage = (slowMs - fastMs) / Math.max(slowMs, 1)
  const preferred: AccountLine =
    better !== previous.preferred && advantage > SWITCH_RATIO ? better : previous.preferred

  return { preferred, measurements: measured.measurements, updatedAt, manual }
}
