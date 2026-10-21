import { useEffect, useRef, useState } from 'react'
import { Check, Copy, Radar } from 'lucide-react'

import { Row } from '@/components/account/Card'
import { QrCode } from '@/components/account/QrCode'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { copyText } from '@/utils/amount'













export function WalletCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const watchRecharge = useAccountStore((state) => state.watchRecharge)
  const stopWatch = useAccountStore((state) => state.stopWatch)

  const [copied, setCopied] = useState(false)
  const [flashing, setFlashing] = useState(false)
  const lastIncreasedAt = useRef<number | null>(null)

  useEffect(() => {
    const at = snapshot?.balanceIncreasedAt ?? null
    if (at === null || at === lastIncreasedAt.current) return
    lastIncreasedAt.current = at
    setFlashing(true)
    const timer = setTimeout(() => setFlashing(false), 2600)
    return () => clearTimeout(timer)
  }, [snapshot?.balanceIncreasedAt])

  if (!snapshot) return null
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const watching = snapshot.watching
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current

  const copyAddress = async () => {
    if (!current?.tron_address) return
    if (await copyText(current.tron_address)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div
      className={
        'rounded-[10px] border bg-panel p-4 transition-colors ' +
        (flashing ? 'border-success/40 bg-success-soft' : 'border-line')
      }
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[13.5px] font-medium text-ink">区块链钱包赞助</h3>
        {watching ? (
          <Badge tone="brand">
            盯单中 · 还剩 {snapshot.watchSecondsLeft}s
          </Badge>
        ) : null}
      </header>

      {




}
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">登录账号后即可赞助。</p>
      ) : (
        <div className="space-y-3">
          {

}

          <div className="rounded-[8px] bg-canvas px-3 py-2">
            <Row label="费率">
              {snapshot.rate ? `1 USDT = ${snapshot.rate} Token` : '——'}
            </Row>
          </div>

          <Row label="赞助地址（TRC20）">
            {current.tron_address ? (
              <button
                type="button"
                onClick={() => void copyAddress()}
                className="group inline-flex items-center gap-1.5 text-ink-soft transition-colors hover:text-brand"
                title="点击复制完整地址"
              >
                <span className="selectable break-all text-right tabular-nums">
                  {current.tron_address}
                </span>
                {copied ? (
                  <Check size={13} className="shrink-0 text-success" />
                ) : (
                  <Copy size={13} className="shrink-0 opacity-60 group-hover:opacity-100" />
                )}
              </button>
            ) : (
              <span className="text-ink-faint">暂时取不到，稍后自动补回</span>
            )}
          </Row>
          {copied ? <p className="text-right text-[11.5px] text-success">已复制</p> : null}

          {current.tron_address ? (
            <div className="flex flex-col items-center gap-2 border-t border-line-soft pt-3">
              <QrCode value={`tron:${current.tron_address}`} size={200} />
              <p className="text-[11.5px] text-ink-faint">用钱包扫码赞助（TRC20）</p>
            </div>
          ) : null}

          {


}
          <div className="flex flex-col items-center gap-2 pt-1">
            {watching ? (
              <Button size="sm" variant="secondary" onClick={() => void stopWatch()}>
                停止盯单
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                icon={<Radar size={13} />}
                disabled={disabled}
                onClick={() => void watchRecharge()}
              >
                开始盯单
              </Button>
            )}
            <p className="text-[12px] font-semibold text-ink-soft">
              转账后请点击「开始盯单」，贡献会自动增加。
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
