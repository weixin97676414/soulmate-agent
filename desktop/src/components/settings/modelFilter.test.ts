import { describe, expect, it } from 'vitest'

import { filterDiscoveredModels } from '@/components/settings/modelFilter'















const SILICONFLOW = 'https://api.siliconflow.cn/v1'


const LIVE = [
  'deepseek-ai/DeepSeek-R1',
  'Qwen/Qwen3-VL-32B-Thinking',
  'Qwen/Qwen3-VL-30B-A3B-Thinking',
  'deepseek-ai/DeepSeek-V4-Flash',
  'deepseek-ai/DeepSeek-V3.2',
  'zai-org/GLM-4.6',
  'Qwen/Qwen3-8B',
  'Qwen/Qwen3-VL-8B-Instruct',
  'moonshotai/Kimi-K2',
]

describe('filterDiscoveredModels · 硅基流动（2026-11-13 起全量显示）', () => {
  it('**一个都不裁剪**：接口给多少就返回多少', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list).toHaveLength(LIVE.length)
    expect([...list].sort()).toEqual([...LIVE].sort())
  })

  it('GLM / Qwen / Kimi / 非 flash 的 deepseek 都在（不再被挡）', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list).toContain('zai-org/GLM-4.6')
    expect(list).toContain('Qwen/Qwen3-8B')
    expect(list).toContain('Qwen/Qwen3-VL-8B-Instruct')
    expect(list).toContain('moonshotai/Kimi-K2')
    expect(list).toContain('deepseek-ai/DeepSeek-V3.2')
  })

  it('第一项是 flash —— 它是「获取模型」后新用户的默认模型', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list[0]).toBe('deepseek-ai/DeepSeek-V4-Flash')
  })

  it('没有 flash 时保持接口原顺序（排序不能把列表打乱）', () => {
    const all = ['zai-org/GLM-4.6', 'moonshotai/Kimi-K2']
    expect(filterDiscoveredModels(SILICONFLOW, all)).toEqual(all)
  })

  it('不改动传入的数组（纯函数）', () => {
    const input = [...LIVE]
    filterDiscoveredModels(SILICONFLOW, input)
    expect(input).toEqual(LIVE)
  })
})

describe('filterDiscoveredModels · 其它服务商', () => {
  it('非硅基流动地址原样返回（一个字节都不动）', () => {
    for (const baseUrl of [
      'https://api.deepseek.com/v1',
      'https://dashscope.aliyuncs.com/compatible-mode/v1',
      'https://api.openai.com/v1',
      'http://127.0.0.1:11434/v1',
    ]) {
      expect(filterDiscoveredModels(baseUrl, LIVE)).toBe(LIVE)
    }
  })

  it('地址里带 siliconflow 才算这一家（大小写不敏感）', () => {
    const list = filterDiscoveredModels('https://API.SiliconFlow.CN/v1', LIVE)
    expect(list[0]).toBe('deepseek-ai/DeepSeek-V4-Flash')
    expect(list).toHaveLength(LIVE.length)
  })
})
