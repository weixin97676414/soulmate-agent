import { useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { AccountCard } from '@/components/account/AccountCard'
// 返佣卡片（CommissionCard）按产品要求**隐藏**，所以这里不再导入它 ——
// 组件文件仍在 `components/account/CommissionCard.tsx`，想恢复时把它加回导入
// 并放开下面渲染处那行注释即可。
import { InviteCard } from '@/components/account/InviteCard'
import { LineCard } from '@/components/account/LineCard'
import { PayPalRechargeCard } from '@/components/account/PayPalRechargeCard'
import { SecurityCard } from '@/components/account/SecurityCard'
import { TokenCard } from '@/components/account/TokenCard'
import { WalletCard } from '@/components/account/WalletCard'
import { WxRechargeCard } from '@/components/account/WxRechargeCard'
import { Button, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import type { AccountPhase } from '@shared/bridge'

/**
 * 「权益」页 —— 账号中心。
 *
 * 产品要求把**所有账号相关的东西**都收在这里（而不是文档原写的"设置 → 账号"）：
 * 账号、密码与安全、我的 Token、邀请码、返佣、余额与赞助、线路。这一页就是
 * "我是谁、有多少、怎么支持"的完整答案，状态行先说清楚当前是什么情况
 * （准备中 / 就绪 / 未联网 / 设备不可用），再让各个卡片各就各位。
 *
 * ⚠️ 口径用「赞助」而不是「充值」（，对齐官网 recharge.html）：
 * Token 是 **Soulmate Agent 开源社区的贡献值**，这里的动作是**支持这个项目**，
 * 不是"购买使用额度"。两个词会在用户心里建起两种完全不同的关系。
 *
 * 设备与账号是一对一绑定的（不存在多账号），所以这里**没有**登录其他账号、
 * 切换账号这类入口 —— 详见 `AccountCard` 的说明。
 */
const STATUS: Record<AccountPhase, { text: string; className: string }> = {
  idle: { text: '正在准备账号…', className: 'text-ink-soft' },
  'checking-network': { text: '正在检查网络…', className: 'text-ink-soft' },
  'probing-line': { text: '正在探测线路…', className: 'text-ink-soft' },
  lookup: { text: '正在检查本机账号…', className: 'text-ink-soft' },
  register: { text: '正在为本机创建账号…', className: 'text-ink-soft' },
  ready: { text: '已就绪', className: 'text-success' },
  offline: { text: '未联网', className: 'text-warning' },
  'device-unusable': { text: '无法识别本机设备', className: 'text-danger' },
  error: { text: '异常', className: 'text-danger' },
}

export function BenefitsPage() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const refresh = useAccountStore((state) => state.refresh)
  const [refreshing, setRefreshing] = useState(false)

  const status = snapshot ? STATUS[snapshot.phase] : STATUS.idle
  const message = snapshot?.message ?? ''
  const busy = snapshot !== null && ['checking-network', 'probing-line', 'lookup', 'register', 'idle'].includes(snapshot.phase)
  // 线路分流（文档 §1）：大陆只显示微信充值，国际只显示 USDT 充值
  const isCn = (snapshot?.line?.preferred ?? 'cn') === 'cn'
  // 账号密码要去哪个官网登录，跟着当前线路走（两条线的账号体系是分开的）
  const siteUrl = isCn ? 'https://china.xinjianxue.com' : 'https://www.xinjianxue.com'

  const onRefresh = async () => {
    setRefreshing(true)
    await refresh()
    setRefreshing(false)
  }

  // 每次进入本页自动刷一次（第 8 条），效果与手点右上角「重试」完全一致。
  //
  // App.tsx 是按视图**条件渲染**本页的（`view === 'benefits' ? <BenefitsPage />`）：
  // 进入权益页即重新挂载，所以 `[]` 依赖正好就是"每次进来刷一次"，不需要另做视图切换事件。
  // `useRef` 防重入：React 严格模式在开发态会把 effect 跑两遍，别因此发两次请求。
  // 设备不可用时**不自动刷**：与按钮的禁用条件对齐（按钮此时本来就点不动），
  // 免得白打一次注定失败的请求。
  const autoRefreshed = useRef(false)
  useEffect(() => {
    if (autoRefreshed.current) return
    autoRefreshed.current = true
    if (snapshot?.deviceUsable === false) return
    // 只在挂载时跑一次：onRefresh 是当次渲染的闭包（内部只用到稳定的 refresh / setRefreshing），
    // 刻意不放进依赖数组，否则每次渲染都会重跑。
    void onRefresh()
  }, [])

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-10 py-6">
      <div className="max-w-[720px]">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            {/* ⚠️ 标题「权益」→「Soulmate Agent 开源社区」：
                左栏那个入口早就叫「社区」了，页面大标题却还停在旧名 ——
                点进去像换了个地方。标点也统一：这一页其它地方写的就是
                「Soulmate Agent 开源社区」（见 TokenCard）。 */}
            <h2 className="text-[15px] font-semibold text-ink">Soulmate Agent 开源社区</h2>
            <span className="flex items-center gap-1.5 text-[12.5px]">
              {busy ? <Spinner className="h-3 w-3" /> : null}
              <span className={status.className}>
                {busy && snapshot ? snapshot.message : status.text}
              </span>
            </span>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={refreshing ? <Spinner /> : <RefreshCw size={13} />}
            disabled={refreshing || !snapshot?.deviceUsable}
            onClick={() => void onRefresh()}
          >
            重试
          </Button>
        </header>

        {/* 一行说明（产品要求）：账号密码的用途。
            大陆与首尔两站的账号体系是分开的，所以网址必须跟着当前线路变 ——
            点一下直接用系统浏览器打开。

            ## 这句话改过两次，别往回改

            · "导出 / 导入" → "获取 / 导入"：搭子与技能组是**官网上
              已有的东西**，用户在这里的动作是"把它拿到本机"；"导出"听着像"先把本机
              的东西导出到官网"（顺序反了）。
            · 口径改成 **"用于开源社区登录、参与活动与交流"**。
              上一版只写"获取 / 导入搭子与技能组" —— 那只是其中一个用途，而用户
              实际在做的事（在社区里参与活动、和人交流）一个都没提，读起来像
              "设密码只为了导东西"。口径与 `SecurityCard` / `PasswordModal` 三处一致。

            ⚠️ "本应用不支持在其它设备登录"这半句**必须留着**：它是账号与本机
            一对一绑定那条产品约束的唯一提示（见 `AccountCard` 的文件头），
            删了会有人来问"怎么在新电脑上登录"。
        */}
        <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">
          账号密码用于开源社区登录、参与活动与交流（
          <button
            type="button"
            onClick={() => void window.agentBridge?.openExternal(siteUrl)}
            className="text-brand hover:underline"
          >
            {siteUrl}
          </button>
          ）；本应用不支持在其它设备登录。
        </p>

        {snapshot && snapshot.phase === 'error' && message ? (
          <p className="mt-3 rounded-[8px] border border-danger/30 bg-danger-soft px-3 py-2 text-[12.5px] text-danger">
            {message}
          </p>
        ) : null}

        <div className="mt-4 space-y-3">
          <AccountCard />
          <SecurityCard />
          <TokenCard />
          {/* 邀请码排在充值之前：返佣必须先把邀请关系建好才生效（清单 §6），
              放在充值上面让用户"先填码、再充值"的顺序一眼可见。
              返佣紧跟邀请：这两块讲的是同一件事（拉人 → 拿钱），分开放反而要来回找。 */}
          <InviteCard />
          {/* PayPal 充值只在首尔线渲染（文档 §1：按线路只显示对应的一套）。
              它是"花钱买到 Token"的直接渠道，排在后面几块之前 —— 先给用户能立刻
              用的路，再讲别的。真正的线路闸在主进程（engine 的 paypalLineGate），
              这里只是不给渲染。 */}
          {!isCn ? <PayPalRechargeCard /> : null}
          {/*
            ⚠️ `<CommissionCard />`（返佣）按产品要求**隐藏**。
            保留组件文件与导入注释，是因为这是"这一版先不露出"，不是功能下线 ——
            直接删组件会让将来想恢复的人从零再写一遍。
            想恢复：把下面这行注释放开即可。
          */}
          {/* <CommissionCard /> */}
          {isCn ? <WxRechargeCard /> : <WalletCard />}
          <LineCard />
        </div>
      </div>
    </div>
  )
}
