import { describe, expect, it } from 'vitest'

import { WELCOME_PRESETS, welcomePresetsFor } from '@/components/chat/welcomePresets'
















const BUILTIN_IDS = [
  'soulmate',
  'LoveBuddy',
  'RelationBuddy',
  'BuddyManager',
  'FortuneTellingBuddy',
]

describe('WELCOME_PRESETS 数据', () => {
  it('五个内置搭子一个都不少', () => {
    for (const id of BUILTIN_IDS) {
      expect(Object.keys(WELCOME_PRESETS)).toContain(id)
    }
  })

  it('每个内置搭子正好三条', () => {
    for (const id of BUILTIN_IDS) {
      expect(WELCOME_PRESETS[id]).toHaveLength(3)
    }
  })

  it('label 与 template 都非空，且都不带句末句号', () => {
    for (const id of BUILTIN_IDS) {
      for (const preset of WELCOME_PRESETS[id]) {
        expect(preset.label.trim()).not.toBe('')
        expect(preset.template.trim()).not.toBe('')
        
        expect(preset.label.endsWith('。')).toBe(false)
        expect(preset.template.trimEnd().endsWith('。')).toBe(false)
      }
    }
  })

  it('label 控制在 14 字以内（窄窗下按钮也放得下）', () => {
    for (const id of BUILTIN_IDS) {
      for (const preset of WELCOME_PRESETS[id]) {
        expect(preset.label.length).toBeLessThanOrEqual(14)
      }
    }
  })

  it('第 42 批删掉的旧文案不许回来', () => {
    const all = JSON.stringify(WELCOME_PRESETS)
    expect(all).not.toContain('我可以调用工具完成实际任务')
  })

  it('同一个搭子内三条 template 互不重复（复制粘贴串行会让用户点两次发同一句）', () => {
    for (const id of BUILTIN_IDS) {
      const templates = WELCOME_PRESETS[id].map((preset) => preset.template)
      expect(new Set(templates).size).toBe(3)
    }
  })

  it('文案是 2026-10-21 用户给的那一版（抽查四条，防被"顺手润色"）', () => {
    expect(WELCOME_PRESETS.BuddyManager[0].label).toBe('搭子助手')
    expect(WELCOME_PRESETS.BuddyManager[0].template).toBe(
      '我需要一个搭子助手，你给我一个完整模板我来填写',
    )
    expect(WELCOME_PRESETS.soulmate[0].label).toBe('首次邂逅')
    expect(WELCOME_PRESETS.soulmate[2].label).toBe('当下建议')
    expect(WELCOME_PRESETS.LoveBuddy[1].label).toBe('情感档案')
    expect(WELCOME_PRESETS.RelationBuddy[1].label).toBe('社交档案')
    
    expect(WELCOME_PRESETS.FortuneTellingBuddy.map((item) => item.label)).toEqual([
      '首次使用',
      '近期运势',
      '事件预测',
    ])
    expect(WELCOME_PRESETS.FortuneTellingBuddy[0].template).toBe(
      '我第一次使用你，给我详细说说八字、占星、梅花、塔罗使用的时候都需要我提供什么以及需要注意什么？',
    )
    expect(WELCOME_PRESETS.FortuneTellingBuddy[1].template).toBe(
      '我希望你能帮我分析下我的近期运势，我需要给你提供什么信息？',
    )
    expect(WELCOME_PRESETS.FortuneTellingBuddy[2].template).toBe(
      '我想请你帮我占卜预测一件事，需要我提供给你什么以及需要注意些什么？',
    )
  })

  it('算命占卜那三条不许在按钮里直接起盘（一次排盘就是一份计费报告）', () => {
    for (const preset of WELCOME_PRESETS.FortuneTellingBuddy) {
      
      expect(preset.template).toMatch(/提供|需要注意/)
      expect(preset.template).not.toMatch(/帮我(排|抽|起卦|洗牌)/)
    }
  })
})

describe('welcomePresetsFor', () => {
  const builtin = (id: string) => ({ id, builtin: true })

  it('内置搭子拿到自己的三条', () => {
    expect(welcomePresetsFor(builtin('soulmate'))).toHaveLength(3)
    expect(welcomePresetsFor(builtin('BuddyManager'))).toHaveLength(3)
    expect(welcomePresetsFor(builtin('FortuneTellingBuddy'))).toHaveLength(3)
  })

  it('自建搭子不摆预设', () => {
    expect(welcomePresetsFor({ id: 'my-own', builtin: false })).toEqual([])
  })

  it('搭子还没加载出来时返回空数组', () => {
    expect(welcomePresetsFor(undefined)).toEqual([])
  })

  it('内置 id 但数据里没有（例如新增了内置搭子忘了配）→ 空数组', () => {
    expect(welcomePresetsFor(builtin('SomeNewBuddy'))).toEqual([])
  })
})
