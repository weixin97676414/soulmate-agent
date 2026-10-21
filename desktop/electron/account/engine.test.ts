import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'


























const hoisted = vi.hoisted(() => ({
  
  userData: '',
  logDesktop: vi.fn(),
  
  isDeviceUsable: vi.fn(() => true),
  




  api: {
    ping: vi.fn(),
    fetchRate: vi.fn(),
    login: vi.fn(),
    lookup: vi.fn(),
    register: vi.fn(),
    claimDeviceKey: vi.fn(),
    deviceSession: vi.fn(),
    fetchAccount: vi.fn(),
    fetchWallet: vi.fn(),
    fetchCommission: vi.fn(),
    invite: vi.fn(),
    redeemCode: vi.fn(),
    recoverAccount: vi.fn(),
    renameAccount: vi.fn(),
    setPassword: vi.fn(),
    watchRecharge: vi.fn(),
    withdrawRmb: vi.fn(),
    withdrawUsdt: vi.fn(),
    wxCreateOrder: vi.fn(),
    wxQueryOrder: vi.fn(),
    paypalConfig: vi.fn(),
    paypalSession: vi.fn(),
    paypalStatus: vi.fn(),
  },
}))

vi.mock('electron', () => ({
  app: {
    getPath: () => hoisted.userData,
    getName: () => 'Soulmate Agent',
    getVersion: () => '0.0.1',
  },
  safeStorage: {
    isEncryptionAvailable: () => true,
    encryptString: (plain: string) => Buffer.from(`enc:${plain}`, 'utf8'),
    decryptString: (buffer: Buffer) => buffer.toString('utf8').replace(/^enc:/, ''),
  },
  shell: { openExternal: vi.fn(async () => undefined) },
}))

vi.mock('../desktop-log', () => ({ logDesktop: hoisted.logDesktop }))

vi.mock('./device', () => ({
  isDeviceUsable: hoisted.isDeviceUsable,
  collectDeviceInfo: vi.fn(async () => ({})),
  resetDeviceInfoCache: vi.fn(),
  deviceSignHeaders: vi.fn(() => ({})),
}))

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  
  return { ...actual, ...hoisted.api }
})

import { AccountEngine } from './engine'

let tmpDir = ''

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'soulmate-engine-'))
  hoisted.userData = tmpDir
  hoisted.logDesktop.mockReset()
  hoisted.isDeviceUsable.mockReset()
  hoisted.isDeviceUsable.mockReturnValue(true)
  for (const fn of Object.values(hoisted.api)) fn.mockReset()
})

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true })
  delete process.env.SOULMATE_ACCOUNT_DISABLED
})

function makeEngine() {
  const notify = vi.fn()
  const paypalHost = { open: vi.fn(), close: vi.fn() }
  const engine = new AccountEngine(notify, paypalHost)
  return { engine, notify, paypalHost }
}

describe('微信充值的金额闸', () => {
  it('非整数 / 不足 1 元 / 超出上限都被拒，且**不发起下单**', async () => {
    const { engine } = makeEngine()

    
    
    const tooLarge = 1_000_000_000
    for (const bad of [0, 1.5, tooLarge]) {
      const result = await engine.createWxRecharge(bad)
      expect(result.ok, `${bad} 元应当被拒`).toBe(false)
      expect(result.error ?? '').toContain('整数')
    }

    
    expect(hoisted.api.wxCreateOrder).not.toHaveBeenCalled()
  })
})

describe('微信充值的线路闸', () => {
  it('切到首尔线路后拒绝下单（微信只在大陆线路开放），同样不联网', async () => {
    const { engine } = makeEngine()
    await engine.setAccountLine('seoul')

    const result = await engine.createWxRecharge(50)
    expect(result.ok).toBe(false)
    expect(result.error ?? '').toContain('大陆线路')
    expect(hoisted.api.wxCreateOrder).not.toHaveBeenCalled()
  })
})

describe('切线路时的支付状态清理', () => {
  it('线路换了、上一套支付提示也清掉了（不会让用户对着失效的订单付款）', async () => {
    const { engine, notify, paypalHost } = makeEngine()
    await engine.setAccountLine('cn')

    
    
    
    const gated = await engine.loadPaypalConfig()
    expect(gated.ok).toBe(false)
    expect(engine.snapshot().paypalNotice, '没造出非空状态，这条用例就没有约束力').not.toBeNull()

    const closedBefore = paypalHost.close.mock.calls.length
    await engine.setAccountLine('seoul')

    const snapshot = engine.snapshot()
    expect(snapshot.line?.preferred).toBe('seoul')
    
    expect(snapshot.line?.manual).toBe(true)
    
    
    expect(snapshot.paypalNotice).toBeNull()
    expect(snapshot.wxOrder).toBeNull()
    expect(snapshot.paypalOrder).toBeNull()
    expect(snapshot.paypalConfig).toBeNull()
    
    expect(paypalHost.close.mock.calls.length).toBeGreaterThan(closedBefore)
    
    expect(notify).toHaveBeenCalled()
  })
})

describe('退出时的收尾', () => {
  it('stop() 会把结账窗口一起收掉', () => {
    const { engine, paypalHost } = makeEngine()

    engine.stop()

    
    expect(paypalHost.close).toHaveBeenCalledTimes(1)
  })
})

describe('关闭账号网络的逃生门', () => {
  it('SOULMATE_ACCOUNT_DISABLED=1 时首启根本不进入启动流程', async () => {
    
    
    
    
    
    
    
    
    
    process.env.SOULMATE_ACCOUNT_DISABLED = '1'
    hoisted.isDeviceUsable.mockReturnValue(false)
    const { engine, notify } = makeEngine()

    engine.start()
    await new Promise((resolve) => setTimeout(resolve, 120))

    expect(hoisted.logDesktop).not.toHaveBeenCalledWith(
      expect.stringContaining('设备主判据全空'),
    )
    
    expect(hoisted.logDesktop).toHaveBeenCalledWith(
      expect.stringContaining('跳过账号首启'),
    )
    
    expect(notify).toHaveBeenCalled()
  })
})
