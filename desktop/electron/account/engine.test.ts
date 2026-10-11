import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

/**
 * 账号引擎的**行为级**单测（第 95 批，产品要求）。
 *
 * ## 这个文件为什么重要
 *
 * `engine.ts` 是主进程里的**真钱**路径（登录 / 邀请码 / 兑换 / 微信充值 / PayPal 结算），
 * 而它此前只有两类"证据"：打包闸里"源码中还有没有那句话"的结构断言，以及**人肉点一遍**。
 * 人肉点不出的恰恰是这几种：金额闸的边界、切线路之后旧的支付状态有没有清干净、
 * 退出时结账窗口有没有收、以及"关掉账号网络"那个逃生门是不是真的关上了。
 * 它们出错都**不会报错**，只会让用户对着一个失效的订单付款、或者让打包验收
 * 打到生产后端去建一个真账号。
 *
 * ## 替身策略
 *
 * - `electron`：`app.getPath` 指向每个用例自己的临时目录（账号文件与密钥都落在那里），
 *   `safeStorage` 用内存实现（真实实现绑 Windows DPAPI，在 CI / 测试机上不可用）。
 * - `./api`：**全部网络函数换成替身**（保留其余导出）—— 用例因此可以断言
 *   "该发的请求发了、不该发的一条都没发"，而且永远不联网。
 * - `./device`：设备指纹要跑系统命令，换掉。
 * - `../desktop-log`：它写的是主进程日志文件，换掉并在个别用例里断言"留下了痕迹"。
 *
 * ⚠️ 这里**只测行为，不测实现**：断言的是"结果对不对 / 有没有发请求"，
 * 而不是"某个私有字段等于什么"。私有字段改名不该让这些用例变红。
 */

const hoisted = vi.hoisted(() => ({
  /** 每个用例一个临时 userData 目录 */
  userData: '',
  logDesktop: vi.fn(),
  /** 设备判据：默认可用；个别用例把它翻成不可用，用来观察"启动流程到底跑没跑" */
  isDeviceUsable: vi.fn(() => true),
  /**
   * engine 会调到的**每一个**网络函数。全列出来的意义：
   * "关闭账号网络"那条用例要逐个数它们有没有被调用 —— 漏列一个，
   * 那条断言就守不住它漏掉的那个。
   */
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
  // 保留 `baseFor` / `AccountApiError` / 常量等非网络导出，只把网络函数换成替身
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

    // ⚠️ 逐个走一遍边界。金额闸在 `requireUser()` **之前**，所以这些用例不需要登录态 ——
    // 这正是它容易被绕过的原因：谁把顺序调一下，未登录也能把请求发出去。
    const tooLarge = 1_000_000_000
    for (const bad of [0, 1.5, tooLarge]) {
      const result = await engine.createWxRecharge(bad)
      expect(result.ok, `${bad} 元应当被拒`).toBe(false)
      expect(result.error ?? '').toContain('整数')
    }

    // 被拒的同时绝不能已经把请求发出去了
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

    // 先**造出一个真实的非空支付态**，否则下面那句"切完是空的"是恒真断言、什么都守不住。
    // 走 `loadPaypalConfig` 的线路闸：它排在 `requireUser()` **之前** ——
    // 所以这一步既不需要登录态，也不会联网，却会真的把一句提示写进快照。
    const gated = await engine.loadPaypalConfig()
    expect(gated.ok).toBe(false)
    expect(engine.snapshot().paypalNotice, '没造出非空状态，这条用例就没有约束力').not.toBeNull()

    const closedBefore = paypalHost.close.mock.calls.length
    await engine.setAccountLine('seoul')

    const snapshot = engine.snapshot()
    expect(snapshot.line?.preferred).toBe('seoul')
    // 手动切过要记下来：否则下次启动的自动测速会把它改回去，用户会觉得"设了没用"
    expect(snapshot.line?.manual).toBe(true)
    // ⚠️ 这些是上一套线路/账号的支付态。切走之后还留着，用户会以为那笔还在进行中，
    // 甚至对着一个已经失效的码付款 —— 所以逐个钉住。
    expect(snapshot.paypalNotice).toBeNull()
    expect(snapshot.wxOrder).toBeNull()
    expect(snapshot.paypalOrder).toBeNull()
    expect(snapshot.paypalConfig).toBeNull()
    // 结账窗口也要收掉（引擎只发号施令，开/关由壳执行）
    expect(paypalHost.close.mock.calls.length).toBeGreaterThan(closedBefore)
    // 新状态必须推给界面，否则用户看到的还是旧线路
    expect(notify).toHaveBeenCalled()
  })
})

describe('退出时的收尾', () => {
  it('stop() 会把结账窗口一起收掉', () => {
    const { engine, paypalHost } = makeEngine()

    engine.stop()

    // 不收的话会挂着一个没人再轮询的 PayPal 页面（白占一个窗口 + 一个进程内的定时器）
    expect(paypalHost.close).toHaveBeenCalledTimes(1)
  })
})

describe('关闭账号网络的逃生门', () => {
  it('SOULMATE_ACCOUNT_DISABLED=1 时首启根本不进入启动流程', async () => {
    // 打包验收脚本靠这个开关保证"验证过程不去生产后端建真账号"。
    // 它一旦失效，表现是**验收过程中悄悄多出一个账号**，而不是测试变红 ——
    // 所以必须有用例守。
    //
    // ⚠️ 怎么"看见"它：**不能**去等"有没有网络请求"。`boot()` 在网络之前还有一段
    // **耗时不可控**的探测（网卡 / DNS / 握手），等 1 秒也可能还没走到发请求那一步 ——
    // 实测"把逃生门去掉"的实现照样通过，那条断言**守不住任何东西**（反向验证当场戳穿）。
    // 改成让"启动流程真的跑起来"留下一个**确定性**痕迹：把设备判据翻成不可用 ——
    // 它是 `boot()` 最早的分支之一（在网络探测之前），一跑就会留下一条固定日志。
    process.env.SOULMATE_ACCOUNT_DISABLED = '1'
    hoisted.isDeviceUsable.mockReturnValue(false)
    const { engine, notify } = makeEngine()

    engine.start()
    await new Promise((resolve) => setTimeout(resolve, 120))

    expect(hoisted.logDesktop).not.toHaveBeenCalledWith(
      expect.stringContaining('设备主判据全空'),
    )
    // 留痕：出问题时日志里要能看出"这次是有意关掉的"，而不是"它自己没动静"
    expect(hoisted.logDesktop).toHaveBeenCalledWith(
      expect.stringContaining('跳过账号首启'),
    )
    // 界面仍要拿到一张快照（否则账号区一片空白，看起来像崩了）
    expect(notify).toHaveBeenCalled()
  })
})
