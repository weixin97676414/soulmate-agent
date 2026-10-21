























import { useEffect, useRef } from 'react'
import { create } from 'zustand'


const closers = new Map<string, () => void>()

interface TransientDialogsState {
  
  openCount: number
  sync: () => void
}

export const useTransientDialogsStore = create<TransientDialogsState>((set) => ({
  openCount: 0,
  sync: () => set({ openCount: closers.size }),
}))









export function useClosableDialog(id: string, open: boolean, close: () => void): void {
  const sync = useTransientDialogsStore((state) => state.sync)
  const closeRef = useRef(close)
  closeRef.current = close

  useEffect(() => {
    if (open) {
      closers.set(id, () => closeRef.current())
    } else {
      closers.delete(id)
    }
    sync()
    return () => {
      closers.delete(id)
      sync()
    }
  }, [id, open, sync])
}







export function closeAllTransientDialogs(): number {
  const pending = [...closers.values()]
  for (const close of pending) {
    try {
      close()
    } catch {
      
    }
  }
  return pending.length
}
