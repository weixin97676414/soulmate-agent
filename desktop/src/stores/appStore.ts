import {
  THEME_IDS,
  isDarkTheme,
  type AppInfo,
  type BackendInfo,
  type BackendStatus,
  type CloseAction,
  type ThemeId,
} from '@shared/bridge'
import { create } from 'zustand'

import { AgentApi } from '@/services/api'



import { useModelHubStore } from '@/stores/modelHubStore'
import { useNotificationStore } from '@/stores/notificationStore'
import type {
  AppSettings,
  BackendHealth,
  ModelInfo,
  PathsInfo,
  ProviderPreset,
  SkillInfo,
} from '@/types'













export type ViewKey =
  | 'chat'
  | 'groups'
  | 'models'
  
  
  | 'tasks'
  | 'appearance'
  | 'skills'
  | 'mcp'
  | 'workspace'
  | 'usage'
  | 'calendar'
  | 'audit'
  | 'preference'
  | 'benefits'
  | 'about'

const THEME_STORAGE_KEY = 'agent-desktop:theme'
const WALLPAPER_STORAGE_KEY = 'agent-desktop:wallpaper'








const BRIDGE_MISSING_MESSAGE =
  '界面与主程序之间的通信桥未建立（预加载脚本未生效）。' +
  '这通常是安装包损坏或版本不匹配导致的，与 Python 环境无关，请重新安装客户端。'







export function resolveTheme(theme: ThemeId): Exclude<ThemeId, 'system'> {
  if (theme !== 'system') return theme
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)')?.matches
  return prefersDark ? 'dark' : 'light'
}











const THEME_CHOSEN_KEY = 'agent-desktop:theme-chosen'








const LEGACY_DEFAULT_THEMES: readonly ThemeId[] = ['sakura', 'dark', 'plum']


function isUserChoice(stored: string | null): stored is string {
  if (!stored) return false
  if (!THEME_IDS.includes(stored as ThemeId)) return false
  
  if (localStorage.getItem(THEME_CHOSEN_KEY) === '1') return true
  
  return !LEGACY_DEFAULT_THEMES.includes(stored as ThemeId)
}

function readStoredTheme(): ThemeId {
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  if (stored === 'system' || isUserChoice(stored)) {
    return stored as ThemeId
  }
  
  
  
  
  
  
  
  
  
  return DAY_DEFAULT
}




const DAY_THEME_KEY = 'agent-desktop:theme-day'
const NIGHT_THEME_KEY = 'agent-desktop:theme-night'










const DAY_DEFAULT: Exclude<ThemeId, 'system'> = 'deepday'
const NIGHT_DEFAULT: Exclude<ThemeId, 'system'> = 'plum'

function readSlot(key: string, fallback: Exclude<ThemeId, 'system'>): Exclude<ThemeId, 'system'> {
  const stored = localStorage.getItem(key)
  
  
  
  if (stored && stored !== 'system' && isUserChoice(stored)) {
    return stored as Exclude<ThemeId, 'system'>
  }
  return fallback
}

export function readDayNightThemes(): {
  day: Exclude<ThemeId, 'system'>
  night: Exclude<ThemeId, 'system'>
} {
  return {
    day: readSlot(DAY_THEME_KEY, DAY_DEFAULT),
    night: readSlot(NIGHT_THEME_KEY, NIGHT_DEFAULT),
  }
}

function writeSlot(key: string, theme: ThemeId): void {
  
  if (theme === 'system') return
  localStorage.setItem(key, theme)
}








function applyWallpaper(dataUrl: string | null): void {
  const root = document.documentElement
  if (!dataUrl) {
    root.style.removeProperty('--app-wallpaper')
    delete root.dataset.wallpaper
    return
  }
  
  const safe = dataUrl.replace(/["'\r\n]/g, '')
  root.style.setProperty('--app-wallpaper', `url("${safe}")`)
  root.dataset.wallpaper = 'on'
}

function readStoredWallpaper(): string | null {
  return localStorage.getItem(WALLPAPER_STORAGE_KEY)
}

function applyTheme(theme: ThemeId): void {
  const resolved = resolveTheme(theme)
  
  document.documentElement.dataset.theme = resolved
  
  document.documentElement.classList.toggle('dark', isDarkTheme(resolved))
  
  window.agentBridge?.setTitleBarTheme(resolved)
  localStorage.setItem(THEME_STORAGE_KEY, theme)
  syncThemeColorMeta()
}













function syncThemeColorMeta(): void {
  const meta = document.querySelector('meta[name="theme-color"]')
  if (!meta) return
  const canvas = getComputedStyle(document.documentElement)
    .getPropertyValue('--app-canvas-solid')
    .trim()
  if (canvas) meta.setAttribute('content', canvas)
}

interface AppState {
  api: AgentApi | null
  backendInfo: BackendInfo | null
  backendStatus: BackendStatus
  appInfo: AppInfo | null
  health: BackendHealth | null

  models: ModelInfo[]
  modelDefaults: { defaultModel: string; effectiveDefault: string }
  presets: ProviderPreset[]
  skills: SkillInfo[]
  settings: AppSettings | null
  paths: PathsInfo | null

  theme: ThemeId
  
  wallpaper: string | null
  






  closeAction: CloseAction
  view: ViewKey
  bootstrapping: boolean
  bootstrapError: string | null
  
















  onboardingActive: boolean

  bootstrap: () => Promise<void>
  restartBackend: () => Promise<void>
  reloadHealth: () => Promise<void>
  reloadModels: () => Promise<void>
  reloadSkills: () => Promise<void>
  reloadSettings: () => Promise<void>
  reloadPaths: () => Promise<void>
  setView: (view: ViewKey) => void
  toggleTheme: () => void
  
  setTheme: (theme: ThemeId) => void
  setWallpaper: (dataUrl: string | null) => void
  
  setCloseAction: (action: CloseAction) => void
  dismissOnboarding: () => void
}









export function hasUsableProvider(models: ModelInfo[]): boolean {
  return models.some(
    (model) => model.enabled && model.provider !== 'ollama' && model.has_api_key,
  )
}













export function needsOnboarding(
  models: ModelInfo[],
  hub: Record<string, { installed: boolean } | undefined>,
): boolean {
  if (!hasUsableProvider(models)) return true
  const voiceMissing = Boolean(hub.voice && !hub.voice.installed)
  const memoryMissing = Boolean(hub.embedding && !hub.embedding.installed)
  return voiceMissing || memoryMissing
}

let bootstrapStarted = false

let rehandshaking = false










async function handshake(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
  info: BackendInfo,
  first = false,
): Promise<void> {
  set({ api: AgentApi.from(info), backendInfo: info })
  
  
  
  await get().reloadModels()
  
  
  
  
  
  
  
  const secondaryReloads: Array<[string, () => Promise<void>]> = [
    ['技能列表', () => get().reloadSkills()],
    ['设置', () => get().reloadSettings()],
    ['路径', () => get().reloadPaths()],
    ['健康检查', () => get().reloadHealth()],
  ]
  const firstPass = await Promise.allSettled(secondaryReloads.map(([, run]) => run()))
  const retried = await Promise.allSettled(
    firstPass.flatMap((outcome, index) =>
      outcome.status === 'rejected' ? [secondaryReloads[index][1]()] : [],
    ),
  )
  for (const outcome of retried) {
    if (outcome.status === 'rejected') {
      console.error(
        '[desktop] 启动时有一项数据没能拉取（已重试过一次），进页面后可手动刷新：',
        outcome.reason,
      )
    }
  }
  
  
  
  
  
  
  try {
    await useModelHubStore.getState().refresh()
  } catch (error) {
    console.error('[desktop] 本地模型状态拉取失败，本次按"未安装"处理：', error)
  }

  if (!needsOnboarding(get().models, useModelHubStore.getState().models)) {
    
    
    set({ onboardingActive: false })
    return
  }
  
  
  
  
  
  if (first || get().onboardingActive) {
    set({ onboardingActive: true })
  }
}


async function rehandshake(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
): Promise<void> {
  if (rehandshaking) return
  rehandshaking = true
  try {
    const info = await window.agentBridge.getBackendInfo()
    const current = get().backendInfo
    
    
    if (current && current.token === info.token) return
    await handshake(set, get, info)
  } catch {
    
    
  } finally {
    rehandshaking = false
  }
}


function watchBackendStatus(
  set: (partial: Partial<AppState>) => void,
  get: () => AppState,
): void {
  
  
  window.agentBridge?.onBackendStatus((status) => {
    const previous = get().backendStatus.state
    set({ backendStatus: status })

    
    if (status.state !== 'ready' || previous === 'ready') return
    
    if (!get().api) return
    void rehandshake(set, get)
  })
}

export const useAppStore = create<AppState>((set, get) => ({
  api: null,
  backendInfo: null,
  backendStatus: { state: 'starting', message: '正在启动智能体核心…' },
  appInfo: null,
  health: null,

  models: [],
  modelDefaults: { defaultModel: '', effectiveDefault: '' },
  presets: [],
  skills: [],
  settings: null,
  paths: null,
  
  
  onboardingActive: false,

  theme: readStoredTheme(),
  wallpaper: readStoredWallpaper(),
  
  
  closeAction: 'ask',
  view: 'chat',
  bootstrapping: true,
  bootstrapError: null,

  
  
  
  bootstrap: async () => {
    
    if (bootstrapStarted) return
    bootstrapStarted = true

    
    
    
    
    
    
    if (!window.agentBridge) {
      set({
        bootstrapping: false,
        bootstrapError: BRIDGE_MISSING_MESSAGE,
        backendStatus: { state: 'failed', message: BRIDGE_MISSING_MESSAGE },
      })
      return
    }

    applyTheme(get().theme)
    applyWallpaper(get().wallpaper)
    watchBackendStatus(set, get)

    
    
    
    window.agentBridge
      .getDesktopPrefs()
      .then((prefs) => set({ closeAction: prefs.closeAction }))
      .catch(() => undefined)

    try {
      const [info, appInfo] = await Promise.all([
        window.agentBridge.getBackendInfo(),
        window.agentBridge.getAppInfo(),
      ])
      set({ appInfo })
      
      await handshake(set, get, info, true)

      set({
        bootstrapping: false,
        backendStatus: { state: 'ready', message: '智能体核心已就绪' },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      set({
        bootstrapping: false,
        bootstrapError: message,
        backendStatus: { state: 'failed', message },
      })
    }
  },

  restartBackend: async () => {
    set({ bootstrapping: true, bootstrapError: null })
    
    
    if (!window.agentBridge) {
      set({ bootstrapping: false, bootstrapError: BRIDGE_MISSING_MESSAGE })
      return
    }
    try {
      const info = await window.agentBridge.restartBackend()
      await handshake(set, get, info)
      set({
        bootstrapping: false,
        backendStatus: { state: 'ready', message: '智能体核心已就绪' },
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      set({ bootstrapping: false, bootstrapError: message })
    }
  },

  reloadHealth: async () => {
    const api = get().api
    if (!api) return
    try {
      set({ health: await api.health() })
    } catch {
      
    }
  },

  reloadModels: async () => {
    const api = get().api
    if (!api) return
    const payload = await api.getModels()
    set({
      models: payload.models,
      modelDefaults: {
        defaultModel: payload.default_model,
        effectiveDefault: payload.effective_default,
      },
      presets: payload.presets ?? [],
    })
  },

  reloadSkills: async () => {
    const api = get().api
    if (!api) return
    const payload = await api.getSkills()
    set({ skills: payload.skills })
  },

  reloadSettings: async () => {
    const api = get().api
    if (!api) return
    set({ settings: await api.getSettings() })
  },

  reloadPaths: async () => {
    const api = get().api
    if (!api) return
    set({ paths: await api.getPaths() })
  },

  
  
  
  setView: (view) => set({ view }),

  toggleTheme: () => {
    
    
    const { day, night } = readDayNightThemes()
    const next = isDarkTheme(get().theme) ? day : night
    applyTheme(next)
    set({ theme: next })
    
    
    
    
    localStorage.setItem(THEME_CHOSEN_KEY, '1')
  },

  setTheme: (theme) => {
    applyTheme(theme)
    set({ theme })
    
    
    if (theme !== 'system') {
      writeSlot(isDarkTheme(theme) ? NIGHT_THEME_KEY : DAY_THEME_KEY, theme)
      
      
      
      localStorage.setItem(THEME_CHOSEN_KEY, '1')
    }
  },

  setWallpaper: (dataUrl) => {
    applyWallpaper(dataUrl)
    if (dataUrl) {
      localStorage.setItem(WALLPAPER_STORAGE_KEY, dataUrl)
    } else {
      localStorage.removeItem(WALLPAPER_STORAGE_KEY)
    }
    set({ wallpaper: dataUrl })
  },

  setCloseAction: (action) => {
    
    
    set({ closeAction: action })

    const bridge = window.agentBridge
    if (!bridge) return
    bridge.setDesktopPrefs({ closeAction: action }).catch(() => {
      
      useNotificationStore.getState().push({
        level: 'warning',
        title: '设置未能保存',
        message: '关闭行为已在本次运行中生效，但可能不会被记住。',
      })
    })
  },

  dismissOnboarding: () => {
    
    
    
    
    
    set({ onboardingActive: false })
  },
}))


export function getApi(): AgentApi {
  const api = useAppStore.getState().api
  if (!api) throw new Error('后端尚未就绪，请稍候重试。')
  return api
}
