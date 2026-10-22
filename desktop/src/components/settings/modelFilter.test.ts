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

describe('filterDiscoveredModels · 硅基流动', () => {
  it('家族规则生效：deepseek + flash 的同族变体自动出现', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list).toEqual(['deepseek-ai/DeepSeek-V4-Flash'])
  })

  it('其它型号仍被挡住（GLM / Qwen / Kimi / 非 flash 的 deepseek）', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list).not.toContain('zai-org/GLM-4.6')
    expect(list).not.toContain('Qwen/Qwen3-8B')
    expect(list).not.toContain('Qwen/Qwen3-VL-8B-Instruct')
    expect(list).not.toContain('moonshotai/Kimi-K2')
    expect(list).not.toContain('deepseek-ai/DeepSeek-V3.2')
  })

  it('第一项是 flash —— 它是「获取模型」后新用户的默认模型', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list[0]).toBe('deepseek-ai/DeepSeek-V4-Flash')
  })

  it('一个都没匹配到 → 退回原列表（给空列表等于说"获取失败"）', () => {
    const all = ['zai-org/GLM-4.6', 'moonshotai/Kimi-K2']
    expect(filterDiscoveredModels(SILICONFLOW, all)).toEqual(all)
  })

  it('回归守卫：2026-10-20 回滚掉的三个模型不许再出现', () => {
    const list = filterDiscoveredModels(SILICONFLOW, LIVE)
    expect(list).not.toContain('deepseek-ai/DeepSeek-R1')
    expect(list).not.toContain('Qwen/Qwen3-VL-32B-Thinking')
    expect(list).not.toContain('Qwen/Qwen3-VL-30B-A3B-Thinking')
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
    expect(filterDiscoveredModels('https://API.SiliconFlow.CN/v1', LIVE)).toEqual([
      'deepseek-ai/DeepSeek-V4-Flash',
    ])
  })
})
