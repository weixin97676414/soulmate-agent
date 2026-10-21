import { useEffect, useState } from 'react'
import { Banknote, RefreshCw } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { WithdrawModal } from '@/components/account/WithdrawModal'
import { Badge, Button, Spinner } from '@/components/ui'
import { formatClock } from '@/lib/time'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'
import type { AccountLine, WithdrawalRecord } from '@shared/bridge'

const STATUS_TONE = { pending: 'warning', done: 'success', rejected: 'danger' } as const
const STATUS_TEXT = { pending: '待审核', done: '已打款', rejected: '已拒绝' } as const


const POLL_MS = 30_000


function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}





function money(line: AccountLine, value: string): string {
  return line === 'cn' ? `¥${value}` : `${formatToken(value)} USDT`
}

function WithdrawalRow({ record, line }: { record: WithdrawalRecord; line: AccountLine }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <div className="text-[12.5px] text-ink">
          {money(line, record.amount)}
          {record.method ? <span className="ml-1.5 text-[11.5px] text-ink-faint">{record.method}</span> : null}
        </div>
        {record.status === 'rejected' && record.admin_note ? (
          <div className="truncate text-[11.5px] text-danger">{record.admin_note}</div>
        ) : (
          <div className="text-[11.5px] text-ink-faint">{record.created_at}</div>
        )}
      </div>
      <Badge tone={STATUS_TONE[record.status]}>{STATUS_TEXT[record.status]}</Badge>
    </div>
  )
}







export function CommissionCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const getCommission = useAccountStore((state) => state.getCommission)
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  





  const [lastManual, setLastManual] = useState<{ at: number; ok: boolean; error: string } | null>(
    null,
  )

  
  
  const currentId = snapshot?.currentId ?? null
  const line = snapshot?.line?.preferred ?? 'cn'
  const canPoll = Boolean(
    snapshot && !snapshot.offline && snapshot.deviceUsable && snapshot.accounts.length > 0,
  )

  






  useEffect(() => {
    if (!canPoll) return
    let timer: number | null = null
    const tick = () => void getCommission()
    const start = () => {
      if (timer !== null) return
      timer = window.setInterval(tick, POLL_MS)
    }
    const stop = () => {
      if (timer === null) return
      window.clearInterval(timer)
      timer = null
    }
    const onVisibility = () => {
      if (document.hidden) {
        stop()
      } else {
        
        tick()
        start()
      }
    }
    tick()
    if (!document.hidden) start()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      stop()
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [canPoll, currentId, line, getCommission])

  if (!snapshot) return null
  const commission = snapshot.commission
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current

  const isRmb = line === 'cn'
  const bucket = isRmb ? commission?.rmb : commission?.usdt
  
  
  const unit = isRmb ? '人民币' : 'USDT（TRC20）'
  const rateText = bucket
    ? `你所邀请的好友进行赞助，你可获得 ${percent(bucket.commission_rate)} ${unit}返佣奖励，可提现。`
    : ''
  
  const error = (lastManual && !lastManual.ok ? lastManual.error : '') || snapshot.commissionError

  






  const refresh = async () => {
    setRefreshing(true)
    const result = await getCommission()
    setRefreshing(false)
    setLastManual({
      at: Date.now(),
      ok: result?.ok !== false,
      error: result?.error ?? '',
    })
  }

  return (
    <Card
      
      
      
      title={isRmb ? '返佣' : 'USDT返佣（TRC20）'}
      actions={
        <Button size="sm" variant="ghost" icon={refreshing ? <Spinner /> : <RefreshCw size={13} />} disabled={disabled || refreshing} onClick={() => void refresh()}>
          刷新
        </Button>
      }
    >
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">登录账号后即可查看返佣。</p>
      ) : !bucket ? (
        <p className="text-[12.5px] text-ink-soft">{disabled ? '未联网，返佣暂不可用。' : '返佣数据暂时取不到，点右上角刷新。'}</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-end justify-between gap-4">
            <div>
              <div className="text-[11.5px] text-ink-faint">可提现佣金</div>
              <div className="text-[22px] font-semibold leading-none tracking-tight text-ink tabular-nums">
                {money(line, bucket.withdrawable)}
              </div>
            </div>
            <Button
              size="sm"
              variant="primary"
              icon={<Banknote size={13} />}
              disabled={disabled}
              onClick={() => setWithdrawOpen(true)}
            >
              提现
            </Button>
          </div>

          {rateText ? (
            <p className="rounded-[8px] bg-canvas px-3 py-2 text-[12px] leading-relaxed text-ink-soft">{rateText}</p>
          ) : null}

          {bucket.withdrawals.length > 0 ? (
            <div className="border-t border-line-soft pt-2">
              <div className="mb-1 text-[11.5px] text-ink-faint">提现记录</div>
              <div className="divide-y divide-line-soft">
                {bucket.withdrawals.map((record) => (
                  <WithdrawalRow key={record.id} record={record} line={line} />
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
      {
}
      {lastManual && lastManual.ok ? (
        <p className="mt-2 text-[11.5px] text-success">
          已更新 · {formatClock(lastManual.at)}
        </p>
      ) : null}
      {error ? (
        <p className="mt-2 text-[11.5px] leading-relaxed text-warning">
          返佣没取到：{error}
          {lastManual && !lastManual.ok ? '' : '（自动刷新会继续重试）'}
        </p>
      ) : null}
      <WithdrawModal open={withdrawOpen} onClose={() => setWithdrawOpen(false)} />
    </Card>
  )
}
