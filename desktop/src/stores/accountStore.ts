









import type {
  AccountActionResult,
  AccountLine,
  AccountSnapshot,
  PayPalResult,
} from '@shared/bridge'
import { create } from 'zustand'

interface AccountState {
  snapshot: AccountSnapshot | null
  
  boot: () => () => void
  refresh: () => Promise<AccountSnapshot | null>
  setLine: (line: AccountLine) => Promise<AccountSnapshot | null>
  reprobeLine: () => Promise<AccountSnapshot | null>
  rename: (name: string, password: string) => Promise<AccountActionResult | null>
  setPassword: (next: string, old: string) => Promise<AccountActionResult | null>
  recover: (account: string, next: string) => Promise<AccountActionResult | null>
  






  login: (account: string, password: string) => Promise<AccountActionResult | null>
  invite: (code: string) => Promise<AccountActionResult | null>
  watchRecharge: () => Promise<AccountActionResult | null>
  stopWatch: () => Promise<void>
  answerOffline: (mode: 'continue' | 'skip') => Promise<void>
  
  getCommission: () => Promise<AccountActionResult | null>
  










  createWx: (amountYuan: number) => Promise<AccountActionResult | null>
  cancelWx: () => Promise<void>
  withdrawRmb: (payload: { amount: number; zhifubao: string; bank: string }) => Promise<AccountActionResult | null>
  withdrawUsdt: (payload: { amount: number; trc20_address: string }) => Promise<AccountActionResult | null>
  
  



  loadPaypal: () => Promise<PayPalResult | null>
  



  createPaypal: (quantity: number) => Promise<PayPalResult | null>
  
  cancelPaypal: () => Promise<void>
  




  dismissPaypalNotice: () => Promise<void>
}

export const useAccountStore = create<AccountState>()((set) => {
  const bridge = (): typeof window.agentBridge | null => window.agentBridge ?? null

  
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
