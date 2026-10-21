

























import { useEffect, useRef } from 'react'
import { create } from 'zustand'

import { getApi } from '@/stores/appStore'
import { VOICE_COMMANDS, commandWord } from '@/services/voiceCommands'

type Handler = () => void | Promise<void>


function normalize(text: string): string {
  return (text ?? '').replace(/[\s，。！？、；：""''《》…—·.,!?;:"'()[\]{}]/g, '')
}

interface VoiceCommandState {
  
  handlers: Map<string, Handler>
  



  register: (id: string, handler: Handler) => () => void
  
  dispatch: (
    text: string,
    overrides: Record<string, string>,
    disabled: string[],
  ) => Promise<boolean>
  
  activeIds: () => string[]
}

export const useVoiceCommandStore = create<VoiceCommandState>((set, get) => ({
  handlers: new Map(),

  register: (id, handler) => {
    const next = new Map(get().handlers)
    next.set(id, handler)
    set({ handlers: next })

    return () => {
      const current = get().handlers
      
      
      
      if (current.get(id) === handler) {
        const cleaned = new Map(current)
        cleaned.delete(id)
        set({ handlers: cleaned })
      }
    }
  },

  dispatch: async (text, overrides, disabled) => {
    const { handlers } = get()
    if (handlers.size === 0) return false

    const pool = VOICE_COMMANDS.filter(
      (spec) => handlers.has(spec.id) && !disabled.includes(spec.id),
    ).map((spec) => ({ id: spec.id, word: commandWord(spec, overrides) }))
    if (pool.length === 0) return false

    const said = normalize(text)
    if (!said) return false

    let hit = pool.find((item) => normalize(item.word) === said)

    if (!hit) {
      
      try {
        const api = getApi()
        const result = await api.matchVoiceCommand(said, pool)
        if (result.id) hit = pool.find((item) => item.id === result.id)
      } catch {
        
        return false
      }
    }
    if (!hit) return false

    const handler = handlers.get(hit.id)
    if (!handler) return false
    await handler()
    return true
  },

  activeIds: () => Array.from(get().handlers.keys()),
}))








export function useVoiceCommand(id: string, handler: Handler | null): void {
  
  
  const latest = useRef(handler)
  latest.current = handler

  
  
  const absent = handler === null

  useEffect(() => {
    if (absent) return
    return useVoiceCommandStore.getState().register(id, () => latest.current?.())
  }, [id, absent])
}
