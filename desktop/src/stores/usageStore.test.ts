
import { describe, expect, it } from 'vitest'

import { budgetStatus } from '@/stores/usageStore'
import type { UsageSummary } from '@/types'









const summary = (budget: number | null | undefined, cost: number | null | undefined) =>
  ({ daily_budget: budget, today: cost === undefined ? undefined : { cost } }) as unknown as UsageSummary

describe('budgetStatus', () => {
  it('没配预算 / 预算为 0 → null（不是"没超"）', () => {
    expect(budgetStatus(null)).toBeNull()
    expect(budgetStatus(summary(null, 1))).toBeNull()
    expect(budgetStatus(summary(undefined, 1))).toBeNull()
    expect(budgetStatus(summary(0, 1))).toBeNull()
  })

  it('还没拿到今日费用 → null（"不知道"与"没超"必须分得开）', () => {
    expect(budgetStatus(summary(10, null))).toBeNull()
    expect(budgetStatus(summary(10, undefined))).toBeNull()
  })

  it('比率与超标判定：刚好等于也算超', () => {
    expect(budgetStatus(summary(10, 2.5))).toMatchObject({ ratio: 0.25, exceeded: false })
    expect(budgetStatus(summary(10, 10))).toMatchObject({ ratio: 1, exceeded: true })
    expect(budgetStatus(summary(10, 11))).toMatchObject({ exceeded: true })
  })

  it('原样把金额递出去（界面要靠它显示花了多少）', () => {
    expect(budgetStatus(summary(10, 2.5))).toMatchObject({ spent: 2.5, budget: 10 })
  })
})
