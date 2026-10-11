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

/** 自动刷新间隔。与"页面不可见时暂停"配合，避免在后台空打接口。 */
const POLL_MS = 30_000

/** 返佣比例是接口返回的（不写死），这里只把它渲染成百分比文案。 */
function percent(rate: number): string {
  return `${Math.round(rate * 100)}%`
}

/**
 * 金额展示。人民币是 2 位小数的金额，**原样展示**（"2.00" 不能变成 "2"）；
 * USDT 是 6 位小数，用 formatToken 去掉尾随 0 更干净。
 */
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

/**
 * 返佣卡：可提现佣金、返佣比例、提现入口、提现记录（文档 §5、§6）。
 *
 * 按当前线路只展示对应那一类：大陆 → 人民币佣金，国际 → USDT 佣金。
 * 返佣比例**来自接口**（`commission_rate`），不写死，避免后端调了比例界面却还显示旧值。
 */
export function CommissionCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const getCommission = useAccountStore((state) => state.getCommission)
  const [withdrawOpen, setWithdrawOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  /**
   * 上一次**手动**刷新的结果（成功 / 失败原因、时刻）。
   *
   * 手动那次必须与自动轮询区分开：自动轮询失败不该每 30 秒往界面上堆一条，
   * 而用户**主动点**的那一次一定要有回音。
   */
  const [lastManual, setLastManual] = useState<{ at: number; ok: boolean; error: string } | null>(
    null,
  )

  // 这些量必须在 `if (!snapshot) return` **之前**算：下面的 useEffect 是 hook，
  // 排在提前 return 之后就违反了 hook 的调用顺序。
  const currentId = snapshot?.currentId ?? null
  const line = snapshot?.line?.preferred ?? 'cn'
  const canPoll = Boolean(
    snapshot && !snapshot.offline && snapshot.deviceUsable && snapshot.accounts.length > 0,
  )

  /**
   * 返佣自动刷新：进页面立刻拉一次，之后每 30 秒一次，页面不可见时暂停。
   *
   * 依赖 `currentId` / `line`：切账号、切线路都要重挂定时器 —— 否则会拿新线路的
   * 数字去比旧线路的展示，甚至把上一个账号的佣金留在界面上。
   * 拉取失败由主进程侧静默处理（佣金是展示性数据），所以这里不需要 try/catch。
   */
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
        // 回到前台先补一次，别让用户盯着一个已经过期的数字
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
  // 单位词与卡片标题保持一致：首尔线是「USDT返佣（TRC20）」，文案里就必须写成
  // USDT（TRC20），否则用户会以为到账的是别的网络上的 USDT（转错链是找不回来的）
  const unit = isRmb ? '人民币' : 'USDT（TRC20）'
  const rateText = bucket
    ? `你所邀请的好友进行赞助，你可获得 ${percent(bucket.commission_rate)} ${unit}返佣奖励，可提现。`
    : ''
  // 失败原因：手动点的那次优先（它是用户当下最关心的），否则用自动刷新留下的
  const error = (lastManual && !lastManual.ok ? lastManual.error : '') || snapshot.commissionError

  /**
   * 手动刷新：**必须给出结果**（成功显示更新时间、失败显示原因）。
   *
   * 原先这里 `await getCommission()` 之后什么都不看 —— 而主进程那边又把异常吞了，
   * 于是"点刷新"= 转个圈、界面毫无变化，用户只能猜（这就是报上来的缺陷）。
   * 现在两边都改了：主进程如实返回 `ok:false` + 原因，这里把它显示出来。
   */
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
      // 标题跟着单位词走：大陆线返佣是人民币，标题写「USDT返佣（TRC20）」会让
      // 标题与正文（¥ 金额、人民币单位）自相矛盾。所以改名只落在首尔线（用户
      // 的更名口径是在"首尔线新增 PayPal"那条里给的），大陆线仍叫「返佣」。
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
      {/* 刷新的回音：手动点过就必须有结果 —— 成功说"什么时候更新的"，
          失败把原因摆出来（原先这里什么都不显示，点了像没反应）。 */}
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
