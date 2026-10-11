import { create } from 'zustand'

import { useAppStore } from '@/stores/appStore'
import type { ModelHubEntry, ModelVerifyResult } from '@/types'

/**
 * 本地模型（语音 / 嵌入）的**下载状态机**。
 *
 * ## 为什么要有这个 store
 *
 * 同一份"下没下、下到几成、装好没有"要在**四个地方**同时显示：
 * 首启引导页的两张卡片、语音设置面板、长期记忆设置区。各自 `useState` 一份的话，
 * 用户在引导页下了模型、转头打开设置页会看到"未安装" —— 而这正是最容易让人
 * 以为"下失败了"的表现。所以状态收在这里，四个地方共用。
 *
 * ## 两条更新通道（都要，不是冗余）
 *
 * 1. **SSE `model_download` 事件**（核心在进度变化时推）—— 让进度条实时动；
 * 2. **轮询 `/v1/models/status`**，只在"有模型正在下"时开（1 秒一次）——
 *    事件流断开、或者最后那条 `done` 恰好丢了时，界面靠它兜底，不会永远停在 99%。
 *
 * 轮询刻意**只在下载中开启**：它每次都会 `stat` 一遍模型文件，平时开着纯属浪费。
 */

/** 下载中的轮询间隔（毫秒）。1 秒与核心的进度节流（≥0.4s/≥1%）是同一个量级。 */
const POLL_MS = 1000

// ⚠️ 用 `number` 而不是 `ReturnType<typeof setInterval>`：本项目同时有 DOM 与 Node
// 的类型声明，后者会把它解析成 Node 的 `Timeout` 对象，赋值时直接类型不符。
let pollTimer: number | null = null

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

interface ModelHubState {
  /** 是否已经成功取过一次状态（没取到之前界面不要显示"未安装"） */
  loaded: boolean
  /** 当前线路（'cn' | 'seoul'）与它的展示名 —— 决定国内/国外源 */
  line: string
  lineTitle: string
  models: Record<string, ModelHubEntry>
  /** 正在发请求（下载/取消/校验）的模型 —— 防连点，不是下载进度 */
  busy: Record<string, boolean>
  verifying: Record<string, boolean>
  /** 「验证一下」与"下载完自动检测"的结果（按模型 id 存） */
  verifyResults: Record<string, ModelVerifyResult>

  refresh: () => Promise<void>
  start: (key: string) => Promise<void>
  cancel: (key: string) => Promise<void>
  verify: (key: string) => Promise<void>
  /** SSE `model_download` 事件的处理入口（见 `notificationStore`） */
  applyDownloadEvent: (data: Record<string, unknown>) => void
}

/** 有任何一个模型正在下载 → 该开轮询了。 */
function anyRunning(models: Record<string, ModelHubEntry>): boolean {
  return Object.values(models).some((item) => item.state === 'running')
}

function withoutKey<T>(source: Record<string, T>, key: string): Record<string, T> {
  const next = { ...source }
  delete next[key]
  return next
}

export const useModelHubStore = create<ModelHubState>((set, get) => {
  /**
   * 把新状态并进 store，并处理两件"顺带的事"：
   * - **下载完成自动检测**（产品要求："下载完成后要给一个自动检测"）；
   * - 轮询该开该关。
   *
   * ⚠️ 自动检测只在 **running → done** 这一次跳变上触发：
   * 挂载时取到的"本来就已经装好"的模型不该被自动加载一遍（嵌入模型 585MB，
   * 加载一次要一两秒且占满 CPU）。
   */
  const merge = (incoming: Record<string, ModelHubEntry>, line?: string, lineTitle?: string) => {
    const previous = get().models
    const finished: string[] = []
    for (const [key, item] of Object.entries(incoming)) {
      if (item.state === 'done' && previous[key]?.state === 'running') finished.push(key)
    }
    set({
      models: incoming,
      ...(line ? { line } : {}),
      ...(lineTitle ? { lineTitle } : {}),
    })
    for (const key of finished) void get().verify(key)
    if (anyRunning(incoming)) {
      if (pollTimer === null) pollTimer = window.setInterval(() => void get().refresh(), POLL_MS)
    } else {
      stopPolling()
    }
  }

  return {
    loaded: false,
    line: '',
    lineTitle: '',
    models: {},
    busy: {},
    verifying: {},
    verifyResults: {},

    refresh: async () => {
      const api = useAppStore.getState().api
      if (!api) return
      try {
        const payload = await api.modelStatus()
        const next: Record<string, ModelHubEntry> = {}
        for (const item of payload.models) next[item.key] = item
        merge(next, payload.line, payload.line_title)
        set({ loaded: true })
      } catch {
        // 取状态失败**不清空已有状态**：一次网络抖动不该让界面从"下到 80%"
        // 跳回"未安装"（那看起来就是"白下了"）。下次轮询/事件会自己纠正。
        stopPolling()
      }
    },

    start: async (key) => {
      const api = useAppStore.getState().api
      if (!api) return
      set((state) => ({
        busy: { ...state.busy, [key]: true },
        // 重新下载 = 上一次的自检结论作废，否则会显示"上次失败的原因"让人误会
        verifyResults: withoutKey(state.verifyResults, key),
      }))
      try {
        await api.downloadModel(key)
        await get().refresh()
      } catch (error) {
        set((state) => ({
          verifyResults: {
            ...state.verifyResults,
            [key]: {
              ok: false,
              reason: 'request-failed',
              detail: error instanceof Error ? error.message : String(error),
            },
          },
        }))
      } finally {
        set((state) => ({ busy: { ...state.busy, [key]: false } }))
      }
    },

    cancel: async (key) => {
      const api = useAppStore.getState().api
      if (!api) return
      set((state) => ({ busy: { ...state.busy, [key]: true } }))
      try {
        await api.cancelModelDownload(key)
        await get().refresh()
      } catch {
        // 取消失败不提示：用户真正的意图是"停下来"，下一轮轮询会显示真实状态
      } finally {
        set((state) => ({ busy: { ...state.busy, [key]: false } }))
      }
    },

    verify: async (key) => {
      const api = useAppStore.getState().api
      if (!api) return
      // 去重：自检是**真加载模型**（嵌入那个 585MB，加载一次要一两秒且占满 CPU），
      // 同时来两次（自动检测 + 用户点「验证一下」）不该各加载一遍。
      if (get().verifying[key]) return
      set((state) => ({ verifying: { ...state.verifying, [key]: true } }))
      try {
        const result = await api.verifyModel(key)
        set((state) => ({ verifyResults: { ...state.verifyResults, [key]: result } }))
      } catch (error) {
        set((state) => ({
          verifyResults: {
            ...state.verifyResults,
            [key]: {
              ok: false,
              reason: 'request-failed',
              detail: error instanceof Error ? error.message : String(error),
            },
          },
        }))
      } finally {
        set((state) => ({ verifying: { ...state.verifying, [key]: false } }))
      }
    },

    applyDownloadEvent: (data) => {
      const key = typeof data.key === 'string' ? data.key : ''
      if (!key) return
      const before = get().models[key]
      const state = (data.state as ModelHubEntry['state']) ?? before?.state ?? 'idle'
      const patch: ModelHubEntry = {
        key,
        title: (data.title as string) ?? before?.title ?? key,
        summary: before?.summary ?? '',
        requirement: before?.requirement ?? '',
        state,
        // 事件里没有 `installed`（那是磁盘结论）：`done` 一定是装好了，
        // 其余情况保留上一次的磁盘结论。
        installed: state === 'done' ? true : Boolean(before?.installed),
        total_bytes: (data.total_bytes as number) ?? before?.total_bytes ?? 0,
        done_bytes: (data.done_bytes as number) ?? before?.done_bytes ?? 0,
        current_file: (data.current_file as string) ?? '',
        speed: (data.speed as number) ?? 0,
        error: (data.error as string) ?? '',
        fallback_used: Boolean(data.fallback_used) || Boolean(before?.fallback_used),
        line: (data.line as string) ?? before?.line ?? null,
        files: before?.files ?? [],
      }
      merge({ ...get().models, [key]: patch })
    },
  }
})
