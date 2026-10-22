import { describe, expect, it } from 'vitest'

import { currencySymbol, formatCost, formatDateTime, formatRate, formatTokens } from '@/lib/format'









describe('formatCost', () => {
  it('null 表示"没配单价"，不是"花了 0 元"', () => {
    
    expect(formatCost(null, 'CNY')).toBe('未配置价格')
  })

  it('不足 1 分钱的非零金额保留 4 位小数', () => {
    
    
    
    expect(formatCost(0.0045, 'CNY')).toBe('¥0.0045')
    expect(formatCost(0.0123, 'CNY')).toBe('¥0.01')
  })

  it('普通金额两位小数，0 也显示两位（不是"未配置"）', () => {
    expect(formatCost(12.3, 'CNY')).toBe('¥12.30')
    expect(formatCost(0, 'CNY')).toBe('¥0.00')
  })

  it('美元用 $ 而不是 US$', () => {
    
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
    
    expect(formatDateTime(at(2026, 1, 2, 3, 5))).toBe('2026/01/02 03:05')
  })
})
