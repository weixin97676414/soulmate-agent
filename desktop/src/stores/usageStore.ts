import { create } from 'zustand'

import { useAppStore } from '@/stores/appStore'
import type { UsageSummary } from '@/types'

interface UsageState {
  summary: UsageSummary | null
  loading: boolean
  
  error: string | null
  load: (days?: number) => Promise<void>
  clear: () => Promise<number>
}

export const useUsageStore = create<UsageState>((set, get) => ({
  summary: null,
  loading: false,
  error: null,

  load: async (days = 30) => {
    const api = useAppStore.getState().api
    if (!api) return
    set({ loading: true, error: null })
    try {
      set({ summary: await api.getUsageSummary(days), loading: false })
    } catch (error) {
      
      
      set({
        loading: false,
        error: error instanceof Error ? error.message : String(error),
      })
    }
  },

  clear: async () => {
    const api = useAppStore.getState().api
    if (!api) return 0
    const result = await api.clearUsage()
    await get().load(get().summary?.window_days ?? 30)
    return result.removed
  },
}))







export function budgetStatus(summary: UsageSummary | null): {
  spent: number
  budget: number
  ratio: number
  exceeded: boolean
} | null {
  const budget = summary?.daily_budget
  const spent = summary?.today?.cost
  if (budget === null || budget === undefined || budget <= 0) return null
  if (spent === null || spent === undefined) return null
  return {
    spent,
    budget,
    ratio: spent / budget,
    exceeded: spent >= budget,
  }
}
