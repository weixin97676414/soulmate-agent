import { create } from 'zustand'

import { BUILTIN_AVATARS, CUSTOM_AVATARS, pickAvatar } from '@/services/avatarPack'
import { useAppStore } from '@/stores/appStore'
import type { AssistantProfile } from '@/types'

interface AssistantState {
  assistants: AssistantProfile[]
  defaultAssistantId: string
  





  legacyIds: Record<string, string>
  
  activeId: string | null
  










  picked: boolean
  loading: boolean

  










  editRequestId: string
  openEditor: (id: string) => void
  clearEditRequest: () => void

  










  newRequest: boolean
  openNewBuddy: () => void
  clearNewRequest: () => void

  load: () => Promise<void>
  setActive: (id: string | null) => void
  preview: (id: string, changes: Partial<AssistantProfile>) => void
  save: (profile: AssistantProfile) => Promise<void>
  remove: (id: string) => Promise<void>
}

function pickInitialAssistant(
  assistants: AssistantProfile[],
  defaultId: string,
): string | null {
  if (assistants.some((item) => item.id === defaultId)) return defaultId
  return assistants[0]?.id ?? null
}























async function assignMissingAvatars(assistants: AssistantProfile[]): Promise<void> {
  const api = useAppStore.getState().api
  if (!api || CUSTOM_AVATARS.length === 0) return

  const used = new Set(assistants.map((item) => item.avatar).filter(Boolean))
  const pending = assistants.filter((item) => !item.avatar && !BUILTIN_AVATARS[item.id])
  if (pending.length === 0) return

  for (const profile of pending) {
    const avatar = pickAvatar(used, profile.id)
    if (!avatar) return
    used.add(avatar)
    try {
      await api.updateAssistant(profile.id, { ...profile, avatar })
      
      useAssistantStore.setState((state) => ({
        assistants: state.assistants.map((item) =>
          item.id === profile.id ? { ...item, avatar } : item,
        ),
      }))
    } catch {
      
    }
  }
}

export const useAssistantStore = create<AssistantState>((set, get) => ({
  assistants: [],
  defaultAssistantId: '',
  
  legacyIds: {},
  activeId: null,
  picked: false,
  loading: false,
  editRequestId: '',
  newRequest: false,

  openEditor: (id) => set({ editRequestId: id }),
  clearEditRequest: () => set({ editRequestId: '' }),
  openNewBuddy: () => set({ newRequest: true }),
  clearNewRequest: () => set({ newRequest: false }),

  load: async () => {
    const api = useAppStore.getState().api
    if (!api) return
    set({ loading: true })
    try {
      const payload = await api.getAssistants()
      set((state) => ({
        assistants: payload.assistants,
        defaultAssistantId: payload.default_assistant,
        legacyIds: payload.legacy_ids ?? {},
        
        activeId:
          state.activeId && payload.assistants.some((item) => item.id === state.activeId)
            ? state.activeId
            : pickInitialAssistant(payload.assistants, payload.default_assistant),
      }))
      
      
      
      void assignMissingAvatars(payload.assistants)
    } finally {
      set({ loading: false })
    }
  },

  
  
  setActive: (id) => set({ activeId: id, picked: true }),

  











  preview: (id, changes) =>
    set((state) => ({
      assistants: state.assistants.map((item) => (item.id === id ? { ...item, ...changes } : item)),
    })),

  save: async (profile) => {
    const api = useAppStore.getState().api
    if (!api) return
    const exists = get().assistants.some((item) => item.id === profile.id)
    if (exists) {
      await api.updateAssistant(profile.id, profile)
    } else {
      await api.createAssistant(profile)
    }
    await get().load()
  },

  remove: async (id) => {
    const api = useAppStore.getState().api
    if (!api) return
    await api.deleteAssistant(id)
    if (get().activeId === id) set({ activeId: null })
    await get().load()
  },

}))


export function useActiveAssistant(): AssistantProfile | null {
  return useAssistantStore((state) => {
    if (!state.activeId) return null
    return state.assistants.find((item) => item.id === state.activeId) ?? null
  })
}
