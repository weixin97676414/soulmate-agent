import { create } from 'zustand'

import { float32ToBase64 } from '@/services/voiceCapture'
import { getApi } from '@/stores/appStore'

export interface VoiceAvailability {
  
  asr: boolean
}

interface VoiceState {
  
  availability: VoiceAvailability | null
  
  transcribing: boolean
  










  refresh: (options?: { force?: boolean }) => Promise<void>
  





  transcribe: (samples: Float32Array, sampleRate: number) => Promise<string>
}

export const useVoiceStore = create<VoiceState>((set, get) => ({
  availability: null,
  transcribing: false,

  refresh: async (options) => {
    
    if (get().availability && !options?.force) return
    try {
      const status = await getApi().voiceStatus()
      set({ availability: { asr: status.asr.available } })
    } catch {
      
      
      
      
      
      
    }
  },

  transcribe: async (samples, sampleRate) => {
    set({ transcribing: true })
    try {
      const result = await getApi().voiceAsr(float32ToBase64(samples), sampleRate)
      return result.text.trim()
    } finally {
      set({ transcribing: false })
    }
  },
}))
