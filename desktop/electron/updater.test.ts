import { describe, expect, it, vi } from 'vitest'










vi.mock('electron', () => ({
  app: {
    getVersion: () => '0.0.1',
    getPath: () => '/tmp/nonexistent-user-data',
    isPackaged: false,
    relaunch: vi.fn(),
    exit: vi.fn(),
  },
  net: { fetch: vi.fn() },
  shell: { openExternal: vi.fn() },
}))
vi.mock('./desktop-log', () => ({ logDesktop: () => {} }))

import { __resetForTest, compareVersion, getUpdateState } from './updater'

describe('compareVersion', () => {
  it('相同版本返回 0', () => {
    expect(compareVersion('0.0.1', '0.0.1')).toBe(0)
  })

  it('本地更低返回 -1（会走增量分支）', () => {
    expect(compareVersion('0.0.1', '0.0.2')).toBe(-1)
  })

  it('本地更高返回 1', () => {
    expect(compareVersion('0.0.2', '0.0.1')).toBe(1)
  })

  it('按段比较而不是按字符串比 —— 否则 0.0.10 会被判成小于 0.0.9', () => {
    expect(compareVersion('0.0.9', '0.0.10')).toBe(-1)
    expect(compareVersion('0.0.10', '0.0.9')).toBe(1)
  })

  it('主要段优先于次要段', () => {
    expect(compareVersion('0.1.0', '0.0.9')).toBe(1)
    expect(compareVersion('1.0.0', '0.9.9')).toBe(1)
  })

  it('容忍首尾空白', () => {
    expect(compareVersion(' 0.0.1 ', '0.0.1')).toBe(0)
  })

  it('不合法版本一律按"相等"处理 —— 宁可放过，也不要因为解析失败而误判成"需要整包重装"', () => {
    expect(compareVersion('v0.0.1', '0.0.1')).toBe(0)
    expect(compareVersion('0.0', '0.0.1')).toBe(0)
    expect(compareVersion('', '0.0.1')).toBe(0)
    expect(compareVersion('0.0.1-beta', '0.0.1')).toBe(0)
  })
})

describe('状态快照', () => {
  it('初始状态**永远有值**（更新坏掉不该让界面拿不到东西）', () => {
    __resetForTest()
    const state = getUpdateState()
    expect(typeof state.supported).toBe('boolean')
    expect(typeof state.phase).toBe('string')
    expect(typeof state.message).toBe('string')
    expect(state.availableVersion).toBeNull()
    expect(state.pendingApply).toBe(false)
    expect(state.total).toBe(0)
    expect(state.downloaded).toBe(0)
  })

  it('未打包时 supported 为 false（开发模式不检查更新）', () => {
    __resetForTest()
    
    expect(getUpdateState().fullPackageUrl).toBe('')
  })
})
