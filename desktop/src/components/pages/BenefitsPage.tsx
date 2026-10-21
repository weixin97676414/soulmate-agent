import { useEffect, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'

import { AccountCard } from '@/components/account/AccountCard'



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
  
  const isCn = (snapshot?.line?.preferred ?? 'cn') === 'cn'
  
  
  
  const communityUrl = isCn
    ? 'https://china.xinjianxue.com/forum.html'
    : 'https://www.xinjianxue.com/forum.html'

  const onRefresh = async () => {
    setRefreshing(true)
    await refresh()
    setRefreshing(false)
  }

  
  
  
  
  
  
  
  const autoRefreshed = useRef(false)
  useEffect(() => {
    if (autoRefreshed.current) return
    autoRefreshed.current = true
    if (snapshot?.deviceUsable === false) return
    
    
    void onRefresh()
  }, [])

  return (
    <div className="flex min-w-0 flex-1 flex-col overflow-y-auto px-10 py-6">
      <div className="max-w-[720px]">
        <header className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-2.5">
            {


}
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

        {
















}
        <p className="mt-1 text-[12px] leading-relaxed text-ink-faint">
          账号密码用于开源社区登录、参与活动与交流（
          <button
            type="button"
            onClick={() => void window.agentBridge?.openExternal(communityUrl)}
            className="text-brand hover:underline"
          >
            {communityUrl}
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
          {

}
          <InviteCard />
          {


}
          {!isCn ? <PayPalRechargeCard /> : null}
          {




}
          {}
          {isCn ? <WxRechargeCard /> : <WalletCard />}
          <LineCard />
        </div>
      </div>
    </div>
  )
}
