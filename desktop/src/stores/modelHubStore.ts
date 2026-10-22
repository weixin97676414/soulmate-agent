import { create } from 'zustand'

import { useAppStore } from '@/stores/appStore'


import { useVoiceStore } from '@/stores/voiceStore'
import type { ModelHubEntry, ModelVerifyResult } from '@/types'





















const POLL_MS = 1000



let pollTimer: number | null = null

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

interface ModelHubState {
  
  loaded: boolean
  
  line: string
  lineTitle: string
  models: Record<string, ModelHubEntry>
  
  busy: Record<string, boolean>
  verifying: Record<string, boolean>
  
  verifyResults: Record<string, ModelVerifyResult>

  refresh: () => Promise<void>
  start: (key: string) => Promise<void>
  cancel: (key: string) => Promise<void>
  verify: (key: string) => Promise<void>
  
  applyDownloadEvent: (data: Record<string, unknown>) => void
}


function anyRunning(models: Record<string, ModelHubEntry>): boolean {
  return Object.values(models).some((item) => item.state === 'running')
}

function withoutKey<T>(source: Record<string, T>, key: string): Record<string, T> {
  const next = { ...source }
  delete next[key]
  return next
}

export const useModelHubStore = create<ModelHubState>((set, get) => {
  








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
    










    if (finished.includes('voice')) {
      void useVoiceStore.getState().refresh({ force: true })
    }
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
        
        
        stopPolling()
      }
    },

    start: async (key) => {
      const api = useAppStore.getState().api
      if (!api) return
      set((state) => ({
        busy: { ...state.busy, [key]: true },
        
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
        
      } finally {
        set((state) => ({ busy: { ...state.busy, [key]: false } }))
      }
    },

    verify: async (key) => {
      const api = useAppStore.getState().api
      if (!api) return
      
      
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
