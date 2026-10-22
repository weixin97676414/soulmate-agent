












import { create } from 'zustand'

interface AvatarPreviewState {
  
  src: string
  
  name: string
  






  assistantId: string
  






  groupId: string
  open: (src: string, name: string, assistantId?: string, groupId?: string) => void
  close: () => void
}

export const useAvatarPreviewStore = create<AvatarPreviewState>((set) => ({
  src: '',
  name: '',
  assistantId: '',
  groupId: '',
  open: (src, name, assistantId = '', groupId = '') => {
    if (src) set({ src, name, assistantId, groupId })
  },
  close: () => set({ src: '', name: '', assistantId: '', groupId: '' }),
}))
