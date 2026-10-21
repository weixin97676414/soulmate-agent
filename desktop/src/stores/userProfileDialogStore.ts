







import { create } from 'zustand'

interface UserProfileDialogState {
  open: boolean
  show: () => void
  hide: () => void
}

export const useUserProfileDialogStore = create<UserProfileDialogState>((set) => ({
  open: false,
  show: () => set({ open: true }),
  hide: () => set({ open: false }),
}))
