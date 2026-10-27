import crypto from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it, vi } from 'vitest'














vi.mock('electron', () => ({
  app: {
    getVersion: () => '1.0.2',
    
    
    getPath: () => process.env.TEMP ?? '/tmp',
    isPackaged: true,
    relaunch: vi.fn(),
    exit: vi.fn(),
  },
  net: { fetch: vi.fn() },
  shell: { openExternal: vi.fn() },
}))
vi.mock('./desktop-log', () => ({ logDesktop: () => {} }))

import { net } from 'electron'
import {
  __resetForTest,
  __seedPendingForTest,
  __setAppliedVersionForTest,
  applyPendingAtBoot,
  checkForUpdate,
  compareVersion,
  getUpdateState,
  initUpdater,
  isDowngrade,
} from './updater'

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

  it('未初始化时 fullPackageUrl 用 LINES 兜底（不依赖清单 / 打桩的 isPackaged）', () => {
    __resetForTest()
    expect(getUpdateState().fullPackageUrl).toContain('Soulmate-Agent-Setup-1.0.2.exe')
  })
})

describe('isDowngrade（防降级判定）', () => {
  it('远端比本机旧 ⇒ 是降级', () => {
    expect(isDowngrade('0.0.1', '1.0.0')).toBe(true)
    expect(isDowngrade('0.9.9', '1.0.0')).toBe(true)
  })

  it('远端更新或相等 ⇒ 不是降级', () => {
    expect(isDowngrade('1.0.0', '1.0.0')).toBe(false)
    expect(isDowngrade('1.1.0', '1.0.0')).toBe(false)
  })

  it('不合法版本按"相等"处理 ⇒ 不当成降级（宁可放过，与 compareVersion 同口径）', () => {
    expect(isDowngrade('', '1.0.0')).toBe(false)
    expect(isDowngrade('v1.0.0', '1.0.0')).toBe(false)
  })
})

describe('检查 / 应用链的防降级（2026-10-22 实测：旧清单被当成"更新"整批下载）', () => {
  const staleManifest = {
    version: '0.0.1',
    min_from: '0.0.1',
    line: 'cn',
    generated_at: '',
    files: [{ target: 'renderer', path: 'x.js', size: 1, sha256: 'a'.repeat(64) }],
  }

  it('清单版本比本机旧 ⇒ 拒绝降级：只拉清单、一个文件都不下载、按钮状态清空', async () => {
    __resetForTest()
    const fetchMock = vi.mocked(net.fetch)
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(new Response(JSON.stringify(staleManifest)))
    initUpdater({ autoUpdate: false }) 
    const state = await checkForUpdate()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(state.phase).toBe('idle')
    expect(state.pendingApply).toBe(false)
    expect(state.availableVersion).toBeNull()
    expect(state.message).toContain('已跳过')
  })

  it('待应用清单比本机旧 ⇒ 启动应用阶段直接丢弃（不碰任何文件）', () => {
    __resetForTest()
    __seedPendingForTest(staleManifest)
    applyPendingAtBoot()
    const state = getUpdateState()
    expect(state.pendingApply).toBe(false)
    expect(state.message).toContain('已忽略')
  })
})

describe('整包地址以清单为准（2026-10-22 修：老客户端去下自己版本的整包）', () => {
  const baseManifest = {
    version: '1.0.3',
    min_from: '1.0.1',
    line: 'cn',
    generated_at: '',
    files: [] as Array<{ target: string; path: string; size: number; sha256: string }>,
  }

  it('清单带 full_package ⇒ fullPackageUrl 用它（不再用客户端写死的地址）', async () => {
    __resetForTest()
    const fetchMock = vi.mocked(net.fetch)
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          ...baseManifest,
          full_package: 'https://example.com/Soulmate-Agent-Setup-1.0.3.exe',
        }),
      ),
    )
    initUpdater({ autoUpdate: false })
    const state = await checkForUpdate()
    expect(state.fullPackageUrl).toBe('https://example.com/Soulmate-Agent-Setup-1.0.3.exe')
  })

  it('清单不带 full_package ⇒ 兜底 LINES（兼容老清单没有该字段）', async () => {
    __resetForTest()
    const fetchMock = vi.mocked(net.fetch)
    fetchMock.mockReset()
    fetchMock.mockResolvedValue(new Response(JSON.stringify(baseManifest)))
    initUpdater({ autoUpdate: false })
    const state = await checkForUpdate()
    expect(state.fullPackageUrl).toContain('Soulmate-Agent-Setup-1.0.2.exe')
  })
})

describe('应用阶段健壮性（预检齐全才替换，防半新半旧）', () => {
  const content = 'hello-new-version'
  const sha = crypto.createHash('sha256').update(content).digest('hex')
  const manifest = {
    version: '1.0.2',
    min_from: '1.0.0',
    line: 'cn',
    generated_at: '',
    files: [{ target: 'renderer', path: 'x.js', size: content.length, sha256: sha }],
  }
  const userData = process.env.TEMP ?? '/tmp'
  const stagingRoot = path.join(userData, 'update-staging')
  const backupRoot = path.join(userData, 'update-backup')

  const withResources = (tmp: string, fn: () => void): void => {
    Object.defineProperty(process, 'resourcesPath', { value: tmp, configurable: true })
    try {
      fn()
    } finally {
      
      Object.defineProperty(process, 'resourcesPath', { value: undefined, configurable: true })
    }
  }

  afterEach(() => {
    fs.rmSync(stagingRoot, { recursive: true, force: true })
    fs.rmSync(backupRoot, { recursive: true, force: true })
  })

  it('暂存区缺文件 ⇒ 一个文件都不动、pending 保留（下次重试）', () => {
    __resetForTest()
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'upd-'))
    withResources(tmp, () => {
      __seedPendingForTest(manifest)
      applyPendingAtBoot()
      const state = getUpdateState()
      expect(state.pendingApply).toBe(true) 
      expect(state.message).toContain('不完整')
      expect(fs.existsSync(path.join(tmp, 'dist', 'x.js'))).toBe(false) 
    })
    fs.rmSync(tmp, { recursive: true, force: true })
  })

  it('暂存区文件 sha 损坏 ⇒ 丢弃 pending，不拿坏文件覆盖', () => {
    __resetForTest()
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'upd-'))
    const bucket = path.join(stagingRoot, sha.slice(0, 2))
    fs.mkdirSync(bucket, { recursive: true })
    fs.writeFileSync(path.join(bucket, `${sha}.bin`), 'corrupted')
    withResources(tmp, () => {
      __seedPendingForTest(manifest)
      applyPendingAtBoot()
      const state = getUpdateState()
      expect(state.pendingApply).toBe(false) 
      expect(state.message).toContain('损坏')
    })
    fs.rmSync(tmp, { recursive: true, force: true })
  })

  it('预检通过后正常替换，并清理旧备份只留 1 个', () => {
    __resetForTest()
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'upd-'))
    fs.mkdirSync(path.join(tmp, 'dist'), { recursive: true })
    fs.writeFileSync(path.join(tmp, 'dist', 'x.js'), 'old')
    const bucket = path.join(stagingRoot, sha.slice(0, 2))
    fs.mkdirSync(bucket, { recursive: true })
    fs.writeFileSync(path.join(bucket, `${sha}.bin`), content)
    
    fs.mkdirSync(path.join(backupRoot, '2000-01-01-old'), { recursive: true })

    withResources(tmp, () => {
      __seedPendingForTest(manifest)
      applyPendingAtBoot()
      const state = getUpdateState()
      expect(state.pendingApply).toBe(false)
      expect(fs.readFileSync(path.join(tmp, 'dist', 'x.js'), 'utf8')).toBe(content)
      expect(fs.readdirSync(backupRoot).length).toBe(1) 
    })
    fs.rmSync(tmp, { recursive: true, force: true })
  })
})

describe('currentVersion：已应用版本只在更高时采用', () => {
  it('appliedVersion 低于安装包版本（1.0.2）⇒ 用安装包版本', () => {
    __resetForTest()
    __setAppliedVersionForTest('1.0.1')
    expect(getUpdateState().version).toBe('1.0.2')
  })

  it('appliedVersion 高于安装包版本 ⇒ 用 appliedVersion', () => {
    __resetForTest()
    __setAppliedVersionForTest('1.0.3')
    expect(getUpdateState().version).toBe('1.0.3')
  })
})
