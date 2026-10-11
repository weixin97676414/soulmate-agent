import { useState } from 'react'
// ``QrCode`` 在这里**必须取别名**：下面第 4 行还从本项目组件里 import 了一个
// 同名的 ``QrCode``（渲染二维码用），不区分就会撞名。
import { QrCode as QrCodeIcon, RefreshCw, Wallet } from 'lucide-react'

import { QrCode } from '@/components/account/QrCode'
import { Badge, Button, Field, Input, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'
import type { WxOrderStatus } from '@shared/bridge'

const STATUS_TEXT: Record<WxOrderStatus, string> = {
  CREATING: '正在向微信下单…',
  NOTPAY: '请用微信扫码支付',
  // ⚠️ 「充值」→「赞助」（按官网 recharge.html 的口径统一）：
  // 这件事的定性是**对开源社区的赞助**，不是"买额度"。用词一点点差别，
  // 用户对"我付出的是什么、换回来的是什么"的理解就完全不同。
  SUCCESS: '赞助成功，已到账',
  CLOSED: '二维码已过期',
  FAIL: '下单失败，请重试',
}

function formatCountdown(seconds: number): string {
  const min = Math.floor(seconds / 60)
  const sec = seconds % 60
  return `${String(min).padStart(2, '0')}:${String(sec).padStart(2, '0')}`
}

/**
 * 微信扫码**赞助**卡（大陆线路）。
 *
 * （文件名仍叫 `WxRechargeCard` —— 改名要同步动一大堆 import，
 * 而它对用户不可见。口径以文案为准。）
 *
 * 到账口径是 1 元 = 1 Token，且以后端 `token_amount` 为准 —— 这里**不做任何
 * 换算**，只把金额作为整数元传上去。轮询在主进程里跑，这里只按 `wxOrder` 状态
 * 展示二维码、倒计时与结局。
 */
export function WxRechargeCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const createWx = useAccountStore((state) => state.createWx)
  const cancelWx = useAccountStore((state) => state.cancelWx)

  const [amount, setAmount] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!snapshot) return null
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const order = snapshot.wxOrder
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current

  // `yuanArg` 给「重新生成」复用：同金额重下单时金额来自旧订单，而不是输入框
  const submit = async (yuanArg?: number) => {
    const yuan = yuanArg ?? Number(amount.trim())
    if (!Number.isInteger(yuan) || yuan < 1 || yuan > 50000) {
      setError('金额必须是 1~50000 的整数（元）。')
      return
    }
    setBusy(true)
    setError('')
    const result = await createWx(yuan)
    setBusy(false)
    if (result === null) {
      setError('界面与主程序之间的通信桥未建立，请重启应用。')
      return
    }
    if (!result.ok) {
      setError(result.error ?? '下单失败。')
      return
    }
    // 成功下单后快照里会带出 wxOrder，卡片自动切到二维码态
  }

  const renderAmount = () => (
    <div className="space-y-3">
      {/* ⚠️ 「到账数以实际为准」→「贡献以实际为准」：
          与"Token 是贡献值"那条定性一致。同一句话里两种说法混用，
          用户会以为"到账"和"贡献"是两个不同的东西。 */}
      <Field label="赞助金额（元）" hint="整数，1 元 = 1 Token，贡献以实际为准。">
        <Input
          type="number"
          value={amount}
          autoComplete="off"
          inputMode="numeric"
          onChange={(event) => {
            setAmount(event.target.value)
            setError('')
          }}
          placeholder="例如 10"
        />
      </Field>
      {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      <Button
        variant="primary"
        icon={busy ? <Spinner /> : <Wallet size={13} />}
        disabled={disabled || busy || !amount.trim()}
        onClick={() => void submit()}
      >
        生成赞助码
      </Button>
    </div>
  )

  const renderOrder = () => {
    if (!order) return null
    const finished = order.status === 'SUCCESS' || order.status === 'CLOSED' || order.status === 'FAIL'
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-center">
          {order.status === 'SUCCESS' ? (
            <div className="flex h-[240px] w-[240px] items-center justify-center rounded-[8px] bg-success-soft text-center">
              <p className="px-6 text-[13px] leading-relaxed text-success">
                已到账 {formatToken(order.token_amount)} Token
              </p>
            </div>
          ) : (
            <QrCode value={order.code_url} />
          )}
        </div>

        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Badge tone={order.status === 'SUCCESS' ? 'success' : order.status === 'NOTPAY' ? 'brand' : 'warning'}>
              {STATUS_TEXT[order.status]}
            </Badge>
            {order.status === 'CREATING' || order.status === 'NOTPAY' ? (
              <span className="text-[12.5px] tabular-nums text-ink-soft">
                还剩 {formatCountdown(order.countdown_seconds)}
              </span>
            ) : null}
          </div>
          {finished ? (
            <Button
              size="sm"
              variant={order.status === 'SUCCESS' ? 'secondary' : 'primary'}
              icon={order.status === 'SUCCESS' ? undefined : <RefreshCw size={13} />}
              disabled={busy}
              onClick={() => {
                if (order.status === 'SUCCESS') {
                  void cancelWx()
                  setAmount('')
                } else {
                  // CLOSED / FAIL：同金额重新下单（走 submit 复用校验 + 错误展示）
                  void submit(order.amount_yuan)
                }
              }}
            >
              {order.status === 'SUCCESS' ? '完成' : '重新生成'}
            </Button>
          ) : (
            <Button size="sm" variant="ghost" onClick={() => void cancelWx()}>
              取消
            </Button>
          )}
        </div>
        <p className="text-[11.5px] leading-relaxed text-ink-faint">
          请用微信「扫一扫」支付；支付成功后贡献会自动增加并刷新贡献值。
        </p>
      </div>
    )
  }

  return (
    <section className="rounded-[10px] border border-line bg-panel p-4">
      <header className="mb-3 flex items-center justify-between gap-3">
        {/* 卡片标题刻意是**中性的「赞助」**而不是「微信赞助」。

            ⚠️ 换过一个理由：这张卡原先装了**两块**（兑换码 + 微信扫码），标题写
            「微信赞助」会让人以为它是"兑换码那一块"的标题 —— 那时选"中性"是为了
            避免这个歧义。

            兑换码已整体剔除，卡里只剩微信扫码一块。标题**仍
            保持中性的「赞助」**：渠道名在下面那行小标题上，而卡头右边写着余额 ——
            用户在这一页要找的是"怎么支持这个项目"，不是"哪个渠道"。 */}
        <h3 className="text-[13.5px] font-medium text-ink">赞助</h3>
        {current ? (
          <span className="text-[12.5px] text-ink-soft">
            社区贡献 <span className="font-semibold text-ink tabular-nums">{formatToken(current.token_balance)}</span> Token
          </span>
        ) : null}
      </header>

      {/* ⚠️ 这里原本是 `<RedeemCodeField />`（兑换码输入块），整体剔除。

          它当时放在最上方（"手上有码的人应该一眼就看到"），而上面那条分隔线也是
          它自带的 —— 所以移除时**不需要补画**：卡片头与内容之间现在只剩
          `<header>` 的 `mb-3`，视觉上已经够了。 */}
      <div className="mb-1.5 flex items-center gap-1.5">
        <QrCodeIcon size={13} className="text-ink-faint" />
        <span className="text-[12.5px] font-medium text-ink-soft">微信扫码赞助</span>
      </div>

      {!current ? <p className="text-[12.5px] text-ink-soft">登录账号后即可赞助。</p> : order ? renderOrder() : renderAmount()}
    </section>
  )
}
