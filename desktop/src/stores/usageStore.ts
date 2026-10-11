import { create } from 'zustand'

import { useAppStore } from '@/stores/appStore'
import type { UsageSummary } from '@/types'

interface UsageState {
  summary: UsageSummary | null
  loading: boolean
  /** 读取失败的原因。**必须展示给用户**，否则统计页一片空白会被误读成"没花过钱" */
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
      // 刻意不静默：读取失败时如果什么都不说，用户看到的是"一个全 0 的页面"，
      // 会以为这个月真的没花过钱。宁可显示错误。
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

/**
 * 距离今日预算还剩多少 / 是否超额。
 *
 * 返回 ``null`` 表示没配预算、或者还没拿到费用数据——
 * 「不知道」和「没超」必须区分开，否则界面会显示"预算充足"而实际上根本没在算。
 */
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
