import { useEffect, useRef, useState } from 'react'
import { CircleDollarSign, Minus, Plus } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { Badge, Button, Input, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'
import type { PayPalNotice, PayPalNoticeTone } from '@shared/bridge'

/**
 * PayPal **赞助**卡（**首尔线路专有**，大陆线路不渲染）。
 *
 * （口径 从"充值"改为"赞助"，对齐官网 recharge.html。）
 *
 * ## 为什么价格一个字都不写死
 *
 * `unit_price` / `min` / `max` / `currency` 全部来自服务端（见 `api.ts` 的说明）：
 * 汇率与限额是运营随时会调的参数。一旦写死在界面里，后端调价之后用户会按**旧价**试算，
 * 付了钱却拿到对不上的 Token —— 这种账目偏差靠事后补偿也补不干净，只能从源头避免。
 * 所以本组件对配置的唯一要求就是"服务端说多少就是多少"。
 *
 * ## 数量 = 美元金额
 *
 * 服务端把「1 USD 换多少 Token」放在 `unit_price` 里，所以这里的数量直接就是**美元金额**：
 * 应付 = quantity 美元，到账 = quantity × unit_price Token。两个数字都是本地算的，
 * 不下发请求 —— 试算要跟手，每打一个数字就发一次请求既慢又没必要。
 *
 * ## 结账为什么在独立窗口
 *
 * PayPal 的授权流程需要自己的浏览会话（第三方 Cookie、重定向回跳），塞进主窗口的 iframe
 * 里会被对方的 CSP/X-Frame-Options 直接挡掉。因此主进程另开一个 460×720 的窗口
 * （见 `main.ts` 的 `openPaypalCheckoutWindow`），本卡片只负责"发起"和"等结果"。
 */

/** 提示配色 → token。配色由主进程按文档 §3 裁决，这里只做映射。 */
const NOTICE_CLASS: Record<PayPalNoticeTone, string> = {
  warning: 'text-warning',
  danger: 'text-danger',
  success: 'text-success',
}

/** 到账闪光时长，与 WalletCard 对齐：同一页面上两处「到账」的节奏必须一致。 */
const FLASH_MS = 2600

/** 货币符号跟随服务端下发的 `currency`，不写死 `$`（后端换币种时界面要跟着变）。 */
function currencyPrefix(currency: string | undefined): string {
  const code = (currency ?? '').trim().toUpperCase()
  if (!code || code === 'USD') return '$'
  return `${code} `
}

/** 秒 → `mm:ss`，给结账窗口的剩余时间用。 */
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

  // 这些量必须在下面的 useEffect / 提前 return **之前**算清：hook 不能排在提前 return 之后
  const config = snapshot?.paypalConfig ?? null
  const notice = snapshot?.paypalNotice ?? null
  const order = snapshot?.paypalOrder ?? null
  const current =
    snapshot?.accounts.find((item) => item.id === snapshot.currentId) ??
    snapshot?.accounts[0] ??
    null
  const blocked = Boolean(snapshot && (snapshot.offline || !snapshot.deviceUsable || !current))

  /**
   * 进卡片就把配置拉下来：单价与上下限全在服务端，没有它既不能试算也不能下单。
   * 失败不在这里提示 —— 主进程已经把原因写进 `paypalNotice`，界面照常画即可。
   */
  useEffect(() => {
    if (config || blocked) return
    void loadPaypal()
  }, [config, blocked, loadPaypal])

  /** 配置到手后把输入框初始化到下限：空着会让「通过 PayPal 赞助」看起来像坏的。 */
  useEffect(() => {
    if (config && text === '') setText(String(config.min))
  }, [config, text])

  /** 「到账闪一下」：监听主进程写入的成功提示（对象引用变化才触发，避免重复闪）。 */
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
  // 两个单价各管一头（产品以文档为准）：到账 = 份数 × unit_price
  // （服务端 unit_tokens），应付 = 份数 × unit_usd —— 数量的单位是"份"，
  // "1 份 = 1 USD"只是早期字段没分开时的巧合，不能再拿来当计算依据。
  const unitPrice = config?.unit_price ?? 0
  const unitUsd = config?.unit_usd ?? 0
  const numeric = Number(text)
  // 输入越界（含空串 / 非数字）只在**用户已经打了字**时才算异常：刚进页面还没输入不该报红
  const outOfRange =
    text.trim() !== '' && (!Number.isFinite(numeric) || numeric < min || numeric > max)
  const quantity =
    Number.isFinite(numeric) && numeric > 0
      ? Math.min(max, Math.max(min, Math.round(numeric)))
      : min
  // 应付：unit_usd 没下发时按 1 份 = 1 USD 兜底（比显示 0 强，且不会误导成"免费"）
  const usd = config ? quantity * (unitUsd > 0 ? unitUsd : 1) : 0
  const payableText = `${currencyPrefix(config?.currency)}${usd.toFixed(2)}`
  const tokenText = formatToken((quantity * unitPrice).toFixed(6))
  const busy = submitting || order?.status === 'PENDING'
  /*
    ⚠️ 这里曾有 `windowMinutes`（把 `order.expires_seconds` 换算成分钟），
    供按钮下方那句"窗口 N 分钟内有效"用。那句话 被产品要求剔除，
    这个变量随之删掉 —— 留着它会是一个"算出来没人用"的值，下一个读代码的人
    还得先确认它到底影响什么。

    有效期本身没丢：等待态那条倒计时（`等待支付 · 还剩 mm:ss`）用的是服务端
    每次轮询下发的 `countdown_seconds`，比这个换算值更准。
  */

  /**
   * 数量一变，上一条提示就过期了实测反馈第 7 条）。
   *
   * 提示记的是"**上一次动作**的结论"：用户把数量改到合法区间后，上一条"数量需在
   * 1–100 之间"的红字还挂着，看起来就像"改完还是错的"。所以只要还挂着提示，
   * 任何一次数量改动都顺手把它擦掉；没有提示时不发这次 IPC。
   */
  const clearStaleNotice = (): void => {
    if (notice) void dismissPaypalNotice()
  }

  /** 把输入收到合法区间。失焦与步进按钮都走它 —— 真实下发给后端的一定是夹紧后的值。 */
  const commit = (value: number): void => {
    setText(String(Math.min(max, Math.max(min, Math.round(value)))))
    clearStaleNotice()
  }

  const submit = async () => {
    // 下单入口先清一次旧提示：本次的结果由主进程写新的，界面不能一边等结果一边挂着上次的红字
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
      // 「充值」→「赞助」：与官网 recharge.html 的口径一致。
      // 这件事的定性是**对开源社区的赞助** —— 用词差别看似很小，但"我是在
      // 买额度"与"我是在支持这个项目"是两种不同的心智，界面上的话术必须一致。
      title="PayPal 赞助"
      flash={flash}
      actions={
        <Badge tone="brand">
          {/* 汇率徽标跟着"每份"口径走：unit_usd=1（当前口径）时恰好就是「1 USD = N Token」，
              以后服务端改了每份美元数，徽标也如实显示，不再写死"1 USD" */}
          {config
            ? unitUsd > 0 && unitUsd !== 1
              ? `${formatToken(String(unitUsd))} USD/份 = ${formatToken(String(unitPrice))} Token`
              : `1 USD = ${formatToken(String(unitPrice))} Token`
            : '汇率获取中…'}
        </Badge>
      }
    >
      <div className="space-y-3">
        {/*
          ⚠️ 这里原本有一行「本渠道无返佣。」，按产品要求**剔除**。

          它是一条"排除式"说明：告诉用户这条路**没有**某个好处。而返佣是
          `InviteCard` 那边的事（拉人 → 拿钱），用户在这一块的心智是"我要支持
          这个项目"，先看到一句"这里不给返佣"只会让人以为**别处都给** ——
          而实际规则并非如此。这类"先说没有什么"的文案，写着像免责、读着像劝退。
        */}

        {/* 数量 + 试算：窄宽度下改上下堆叠，试算块不再被挤成一条 */}
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
              {/* 用 ring 而不是覆盖 border 类：Input 已经带了 border-line，
                  再叠一个 border-danger 谁生效要看 Tailwind 产物顺序，不可靠 */}
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
              {/* 等宽数字：金额跳动时不左右晃 */}
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

        {/* 动作块 */}
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
          {/*
            ⚠️ 这里原本还有一行「结账在独立窗口完成，赞助成功后 Token 自动到账；
            窗口 N 分钟内有效。」按产品要求**整句剔除**。

            它讲的三件事在界面上都已经有了更准的出处：结账窗口一开就是独立窗口
            （看得见）；"到账"由卡里的「到账」试算块与到账闪光负责；有效期在等待态
            那条倒计时里（`等待支付 · 还剩 mm:ss`）。留在这里只会让按钮下方多一行
            要读的文字，而那行字里的 `windowMinutes` 还是**下单前**的缺省值 ——
            它说的是"规则"，用户真正需要的是"我这一单还剩多久"，后者就在旁边。
          */}
        </div>

        {/* 状态块：主进程按文档 §3 对照出的配色 + 文案 */}
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
