import { useEffect, useRef, useState } from 'react'
import { CircleDollarSign, Minus, Plus } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { Badge, Button, Input, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'
import type { PayPalNotice, PayPalNoticeTone } from '@shared/bridge'



























const NOTICE_CLASS: Record<PayPalNoticeTone, string> = {
  warning: 'text-warning',
  danger: 'text-danger',
  success: 'text-success',
}


const FLASH_MS = 2600


function currencyPrefix(currency: string | undefined): string {
  const code = (currency ?? '').trim().toUpperCase()
  if (!code || code === 'USD') return '$'
  return `${code} `
}


function countdown(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds))
  const mm = String(Math.floor(safe / 60)).padStart(2, '0')
  const ss = String(safe % 60).padStart(2, '0')
  return `${mm}:${ss}`
}

export function PayPalRechargeCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const loadPaypal = useAccountStore((state) => state.loadPaypal)
  const createPaypal = useAccountStore((state) => state.createPaypal)
  const cancelPaypal = useAccountStore((state) => state.cancelPaypal)
  const dismissPaypalNotice = useAccountStore((state) => state.dismissPaypalNotice)

  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [flash, setFlash] = useState(false)
  const lastNotice = useRef<PayPalNotice | null>(null)

  
  const config = snapshot?.paypalConfig ?? null
  const notice = snapshot?.paypalNotice ?? null
  const order = snapshot?.paypalOrder ?? null
  const current =
    snapshot?.accounts.find((item) => item.id === snapshot.currentId) ??
    snapshot?.accounts[0] ??
    null
  const blocked = Boolean(snapshot && (snapshot.offline || !snapshot.deviceUsable || !current))

  



  useEffect(() => {
    if (config || blocked) return
    void loadPaypal()
  }, [config, blocked, loadPaypal])

  
  useEffect(() => {
    if (config && text === '') setText(String(config.min))
  }, [config, text])

  
  useEffect(() => {
    if (!notice || notice === lastNotice.current) return
    lastNotice.current = notice
    if (notice.tone !== 'success') return
    setFlash(true)
    const timer = setTimeout(() => setFlash(false), FLASH_MS)
    return () => clearTimeout(timer)
  }, [notice])

  if (!snapshot) return null

  const min = config?.min ?? 1
  const max = config?.max ?? 100
  
  
  
  const unitPrice = config?.unit_price ?? 0
  const unitUsd = config?.unit_usd ?? 0
  const numeric = Number(text)
  
  const outOfRange =
    text.trim() !== '' && (!Number.isFinite(numeric) || numeric < min || numeric > max)
  const quantity =
    Number.isFinite(numeric) && numeric > 0
      ? Math.min(max, Math.max(min, Math.round(numeric)))
      : min
  
  const usd = config ? quantity * (unitUsd > 0 ? unitUsd : 1) : 0
  const payableText = `${currencyPrefix(config?.currency)}${usd.toFixed(2)}`
  const tokenText = formatToken((quantity * unitPrice).toFixed(6))
  const busy = submitting || order?.status === 'PENDING'
  









  






  const clearStaleNotice = (): void => {
    if (notice) void dismissPaypalNotice()
  }

  
  const commit = (value: number): void => {
    setText(String(Math.min(max, Math.max(min, Math.round(value)))))
    clearStaleNotice()
  }

  const submit = async () => {
    
    clearStaleNotice()
    setSubmitting(true)
    await createPaypal(quantity)
    setSubmitting(false)
  }

  const disabledReason = !snapshot.deviceUsable
    ? '无法识别本机设备，暂时不能赞助。'
    : snapshot.offline
      ? '未联网，暂时不能赞助。'
      : !current
        ? '登录账号后即可赞助。'
        : ''

  return (
    <Card
      
      
      
      title="PayPal 赞助"
      flash={flash}
      actions={
        <Badge tone="brand">
          {
}
          {config
            ? unitUsd > 0 && unitUsd !== 1
              ? `${formatToken(String(unitUsd))} USD/份 = ${formatToken(String(unitPrice))} Token`
              : `1 USD = ${formatToken(String(unitPrice))} Token`
            : '汇率获取中…'}
        </Badge>
      }
    >
      <div className="space-y-3">
        {






}

        {}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="sm:flex-1">
            <span className="mb-1.5 block text-[12.5px] font-medium text-ink-soft">赞助数量（USD）</span>
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                aria-label="减少"
                disabled={blocked || busy || quantity <= min}
                onClick={() => commit(quantity - 1)}
              >
                <Minus size={13} />
              </Button>
              {
}
              <div
                className={
                  'min-w-0 flex-1 rounded-[8px] ' +
                  (outOfRange ? 'ring-1 ring-danger' : 'ring-0')
                }
              >
                <Input
                  type="number"
                  inputMode="numeric"
                  min={min}
                  max={max}
                  value={text}
                  disabled={blocked || busy}
                  aria-invalid={outOfRange}
                  className="text-center tabular-nums"
                  onChange={(event) => {
                    setText(event.target.value)
                    clearStaleNotice()
                  }}
                  onBlur={() => commit(quantity)}
                />
              </div>
              <Button
                size="sm"
                variant="secondary"
                aria-label="增加"
                disabled={blocked || busy || quantity >= max}
                onClick={() => commit(quantity + 1)}
              >
                <Plus size={13} />
              </Button>
            </div>
            {outOfRange ? (
              <p className="mt-1 text-[11.5px] text-danger">
                数量需在 {min}–{max} 之间，将按 {quantity} 计算。
              </p>
            ) : null}
          </div>

          <div className="rounded-[8px] bg-canvas px-3 py-2 sm:w-[220px]">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-[12.5px] text-ink-soft">应付</span>
              {}
              <span className="font-mono text-[13px] text-ink tabular-nums">{payableText}</span>
            </div>
            <div className="mt-1 flex items-baseline justify-between gap-3">
              <span className="text-[12.5px] text-ink-soft">到账</span>
              <span className="font-mono text-[13px] font-medium text-brand tabular-nums">
                {tokenText} Token
              </span>
            </div>
          </div>
        </div>

        {}
        <div className="space-y-1.5">
          <Button
            variant="primary"
            icon={submitting ? <Spinner /> : <CircleDollarSign size={13} />}
            className="w-full sm:w-auto"
            disabled={blocked || busy || !config || outOfRange || unitPrice <= 0}
            onClick={() => void submit()}
          >
            {order?.status === 'PENDING' ? '等待支付结果…' : '通过 PayPal 赞助'}
          </Button>
          {








}
        </div>

        {}
        {order?.status === 'PENDING' ? (
          <div className="flex items-center justify-between gap-3 rounded-[8px] bg-canvas px-3 py-2">
            <span className="text-[12.5px] text-ink-soft">
              等待支付 · 还剩 {countdown(order.countdown_seconds)}
            </span>
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void cancelPaypal()}>
              取消本次
            </Button>
          </div>
        ) : null}

        {notice ? (
          <p className={`text-[11.5px] leading-relaxed ${NOTICE_CLASS[notice.tone]}`}>
            {notice.message}
          </p>
        ) : null}

        {disabledReason ? (
          <p className="text-[11.5px] leading-relaxed text-ink-faint">{disabledReason}</p>
        ) : null}
      </div>
    </Card>
  )
}
