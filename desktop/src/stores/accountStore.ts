/**
 * 账号状态的渲染层镜像。
 *
 * ## 为什么"镜像"而不是"源"
 *
 * 账号的**权威数据在主进程**（凭据、签名、请求都只在那里发生）。这个 store 只是
 * 订阅主进程推来的**完整快照**，再把用户动作转发回去 —— 它自己从不拼状态，
 * 也不存凭据。快照是完整的、替换式的，所以渲染层任何时刻拿到的都是一份自洽的
 * 全局状态，不会出现"改了账号但余额还显示上一个"这种增量拼接才有的病。
 */
import type {
  AccountActionResult,
  AccountLine,
  AccountSnapshot,
  PayPalResult,
} from '@shared/bridge'
import { create } from 'zustand'

interface AccountState {
  snapshot: AccountSnapshot | null
  /** 订阅快照变化并拉一次初值。返回退订函数（React 严格模式会跑两次 effect）。 */
  boot: () => () => void
  refresh: () => Promise<AccountSnapshot | null>
  setLine: (line: AccountLine) => Promise<AccountSnapshot | null>
  reprobeLine: () => Promise<AccountSnapshot | null>
  rename: (name: string, password: string) => Promise<AccountActionResult | null>
  setPassword: (next: string, old: string) => Promise<AccountActionResult | null>
  recover: (account: string, next: string) => Promise<AccountActionResult | null>
  /**
   * 用账号 + 密码登录，换一个会话 token。
   *
   * 它不是"登录别的账号"（账号参数只有本机已有的那一个，见 SecurityCard 的入口）：
   * 用途是**恢复本机凭据** —— 设备凭据（`device_secret`）丢失后换不回来（文档 §4.2），
   * 而拿到会话 token 之后就不再需要设备签名，返佣/钱包这些接口也就活了。
   */
  login: (account: string, password: string) => Promise<AccountActionResult | null>
  invite: (code: string) => Promise<AccountActionResult | null>
  watchRecharge: () => Promise<AccountActionResult | null>
  stopWatch: () => Promise<void>
  answerOffline: (mode: 'continue' | 'skip') => Promise<void>
  // ---- 支付 / 返佣 / 提现 ---- //
  getCommission: () => Promise<AccountActionResult | null>
  /*
    ⚠️ 这里曾有 `redeem`（兑换码充值 Token）与 `lastRedeem`。
    按产品要求**整体剔除**（"剔除兑换码功能"）：
    组件 `components/account/RedeemCodeField.tsx` 已删除，两张赞助卡里的入口也移除了。

    **只删了界面这一层**：主进程的 `redeemCode` 通道与后端接口都还在。
    它们是"一条能用的能力"，只是现在没有入口 —— 留着不占用户视野，
    将来要恢复（或换个地方露出）时不必从零再写一遍。
    真要连底层一起删，需要同步动 `shared/bridge.ts` + `electron/preload.ts` +
    账号引擎三处，那是另一件事，别顺手做。
  */
  createWx: (amountYuan: number) => Promise<AccountActionResult | null>
  cancelWx: () => Promise<void>
  withdrawRmb: (payload: { amount: number; zhifubao: string; bank: string }) => Promise<AccountActionResult | null>
  withdrawUsdt: (payload: { amount: number; trc20_address: string }) => Promise<AccountActionResult | null>
  // ---- PayPal 充值（首尔线路专有） ---- //
  /**
   * 取 PayPal 渠道配置（单价 / 数量上下限 / currency）。**价格一律服务端下发**，
   * 界面拿它试算，绝不写死 —— 后端调价后界面必须立刻跟着变。
   */
  loadPaypal: () => Promise<PayPalResult | null>
  /**
   * 发起 PayPal 结账。不共用 `runAction`，因为它要带回按文档 §3 对照出的提示
   * （tone + 文案），界面只照着画。
   */
  createPaypal: (quantity: number) => Promise<PayPalResult | null>
  /** 取消当前 PayPal 结账（关窗 + 停轮询），语义同 `cancelWx`。 */
  cancelPaypal: () => Promise<void>
  /**
   * 清掉当前 PayPal 提示（改数量 / 重新下单之前）。
   *
   * 提示是"上一次动作的结论"：数量一改它就过期了，留着会让用户误以为"改了还是错的"。
   */
  dismissPaypalNotice: () => Promise<void>
}

export const useAccountStore = create<AccountState>()((set) => {
  const bridge = (): typeof window.agentBridge | null => window.agentBridge ?? null

  /** 动作类的统一出口：转发给主进程，并把返回的快照同步进 store。 */
  const runAction = async (
    call: (b: NonNullable<typeof window.agentBridge>) => Promise<AccountActionResult>,
  ): Promise<AccountActionResult | null> => {
    const b = bridge()
    if (!b) return null
    const result = await call(b)
    set({ snapshot: result.snapshot })
    return result
  }

  return {
    snapshot: null,

    boot: () => {
      const b = bridge()
      if (!b) return () => undefined
      // 先拉一次（窗口可能是在引擎已跑完之后才创建的），再订阅后续推送
      void b.getAccountSnapshot().then((snapshot) => set({ snapshot }))
      return b.onAccountChanged((snapshot) => set({ snapshot }))
    },

    refresh: async () => {
      const b = bridge()
      if (!b) return null
      const snapshot = await b.refreshAccount()
      set({ snapshot })
      return snapshot
    },

    setLine: async (line) => {
      const b = bridge()
      if (!b) return null
      const snapshot = await b.setAccountLine(line)
      set({ snapshot })
      return snapshot
    },

    reprobeLine: async () => {
      const b = bridge()
      if (!b) return null
      const snapshot = await b.reprobeAccountLine()
      set({ snapshot })
      return snapshot
    },

    rename: (name, password) => runAction((b) => b.renameAccount(name, password)),
    setPassword: (next, old) => runAction((b) => b.setAccountPassword(next, old)),
    recover: (account, next) => runAction((b) => b.recoverAccount(account, next)),
    login: (account, password) => runAction((b) => b.loginAccount(account, password)),
    invite: (code) => runAction((b) => b.submitInviteCode(code)),

    watchRecharge: () => runAction((b) => b.watchRecharge()),

    stopWatch: async () => {
      const b = bridge()
      if (!b) return
      const snapshot = await b.stopRechargeWatch()
      set({ snapshot })
    },

    answerOffline: async (mode) => {
      const b = bridge()
      if (!b) return
      await b.answerOfflinePrompt(mode)
    },

    getCommission: () => runAction((b) => b.getAccountCommission()),
    createWx: (amountYuan) => runAction((b) => b.createWxRecharge(amountYuan)),
    withdrawRmb: (payload) => runAction((b) => b.withdrawRmb(payload)),
    withdrawUsdt: (payload) => runAction((b) => b.withdrawUsdt(payload)),

    cancelWx: async () => {
      const b = bridge()
      if (!b) return
      const snapshot = await b.cancelWxRecharge()
      set({ snapshot })
    },

    loadPaypal: async () => {
      const b = bridge()
      if (!b) return null
      const result = await b.getPaypalConfig()
      set({ snapshot: result.snapshot })
      return result
    },

    createPaypal: async (quantity) => {
      const b = bridge()
      if (!b) return null
      const result = await b.createPaypalCheckout(quantity)
      set({ snapshot: result.snapshot })
      return result
    },

    cancelPaypal: async () => {
      const b = bridge()
      if (!b) return
      const snapshot = await b.cancelPaypalCheckout()
      set({ snapshot })
    },

    dismissPaypalNotice: async () => {
      const b = bridge()
      if (!b) return
      const snapshot = await b.dismissPaypalNotice()
      set({ snapshot })
    },
  }
})
