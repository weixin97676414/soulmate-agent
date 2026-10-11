import { useEffect, useRef, useState } from 'react'
import { Check, Copy, Radar } from 'lucide-react'

import { Row } from '@/components/account/Card'
import { QrCode } from '@/components/account/QrCode'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { copyText } from '@/utils/amount'

/**
 * 钱包与**赞助**卡（国际线路）：余额、费率、TRC20 地址 + 一键复制 + 本地二维码、盯单状态。
 *
 * （口径 从"充值"改为"赞助"，对齐官网 recharge.html。）
 *
 * 二维码内容按文档 §4.2 用 `tron:<地址>`，扫码器（TRON 钱包 / 主流钱包）能直接识别。
 *
 * ## "到账闪一下"
 *
 * 主进程在轮询里发现余额变大时会把 `balanceIncreasedAt` 戳进快照；这里监听它变化，
 * 给整卡一个短暂的 success 底色 —— 充值到账是这个页面上最该被看见的一件事。
 */
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

      {/*
        ⚠️ 这里原本是 `<RedeemCodeField />`（兑换码输入块），整体剔除。

        国际线路也一样：兑换码是**同一个后端接口**，两条线路同去同留，
        否则会变成"大陆能兑、首尔不能"这种没人能解释的差异。
      */}
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">登录账号后即可赞助。</p>
      ) : (
        <div className="space-y-3">
          {/* ⚠️ 余额展示整块删除：权益页顶部的「我的 Token」
              已经在展示余额，同一页两份大数字只会让人怀疑哪份是准的；
              这张卡只回答"怎么充"。 */}

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

          {/* 盯单按钮放二维码正下方居中，说明移到按钮下方：扫码 → 点按钮 → 到账，
              操作顺序和视觉顺序一致，按钮不再和说明挤在同一行。
              到账不是全自动的：用户转账后必须点一次「开始盯单」，后端才开始盯链上，
              之前写"无需额外操作"是错的，会让人转了钱干等却一直不到账。 */}
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
