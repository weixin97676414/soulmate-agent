import { describe, expect, it } from 'vitest'

import { currencySymbol, formatCost, formatDateTime, formatRate, formatTokens } from '@/lib/format'

/**
 * 设置页格式化与**金额口径**的回归钉（第 92 批，M-36）。
 *
 * 这里测的不是"`Intl` 能不能用"，而是几条**容易被顺手改掉、且改了不会报错**的口径：
 * 小额不能显示成"看起来免费"、`$` 不能变成 `US$`、"不知道价格"不能显示成 0。
 * 它们在界面上只表现为一个数字，没有任何测试会因为它们变红 —— 所以钉在这里。
 */

describe('formatCost', () => {
  it('null 表示"没配单价"，不是"花了 0 元"', () => {
    // 把"不知道"显示成"免费"会直接误导用户的成本决策，而且是用户永远不会发现的那种
    expect(formatCost(null, 'CNY')).toBe('未配置价格')
  })

  it('不足 1 分钱的非零金额保留 4 位小数', () => {
    // ⚠️ 阈值是**1 分钱**，不是"看起来小就多给几位"：
    //   · 0.0045 不足一分 → 4 位（否则会显示成 ¥0.00，看起来像免费）
    //   · 0.0123 已经超过一分 → 仍然两位（**这是既有口径**，换 Intl 时原样保住了）
    expect(formatCost(0.0045, 'CNY')).toBe('¥0.0045')
    expect(formatCost(0.0123, 'CNY')).toBe('¥0.01')
  })

  it('普通金额两位小数，0 也显示两位（不是"未配置"）', () => {
    expect(formatCost(12.3, 'CNY')).toBe('¥12.30')
    expect(formatCost(0, 'CNY')).toBe('¥0.00')
  })

  it('美元用 $ 而不是 US$', () => {
    // 中文区域下 USD 的默认写法是 US$；界面上一直是 $，换实现不该把它一起换掉
    expect(formatCost(1, 'USD')).toBe('$1.00')
  })
})

describe('currencySymbol', () => {
  it('与 formatCost 用的是同一份货币口径', () => {
    expect(currencySymbol('CNY')).toBe('¥')
    expect(currencySymbol('USD')).toBe('$')
  })
})

describe('formatTokens', () => {
  it('中文紧凑写法（万/亿），不是 K/M', () => {
    expect(formatTokens(1_000_000)).toBe('100万')
    expect(formatTokens(12_345)).toBe('1.2万')
    expect(formatTokens(1500)).toBe('1500')
    expect(formatTokens(0)).toBe('0')
  })
})

describe('formatRate', () => {
  it('换算成百分比；没有数据给破折号（"不知道"与"0%"必须分得开）', () => {
    expect(formatRate(0.5)).toBe('50%')
    expect(formatRate(0)).toBe('0%')
    expect(formatRate(null)).toBe('—')
  })
})

describe('formatDateTime', () => {
  // ⚠️ 用**本地时间**构造再断言：跨时区跑测试时，写死的 epoch 会算出另一天
  const at = (y: number, month: number, d: number, h: number, min: number, s = 0) =>
    new Date(y, month - 1, d, h, min, s).getTime() / 1000

  it('默认给完整时刻（带年，24 小时制）', () => {
    expect(formatDateTime(at(2026, 10, 10, 15, 30))).toBe('2026/10/10 15:30')
  })

  it('审计表那档：不带年、带秒', () => {
    expect(formatDateTime(at(2026, 10, 10, 15, 30, 45), { withSeconds: true, withYear: false })).toBe(
      '10/10 15:30:45',
    )
  })

  it('24 小时制不随系统区域漂移', () => {
    // 下午三点**不会**变成 3:30 PM —— 表格里两种写法混着看很容易读错
    expect(formatDateTime(at(2026, 1, 2, 3, 5))).toBe('2026/01/02 03:05')
  })
})
