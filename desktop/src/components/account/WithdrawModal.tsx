import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 提现弹窗（文档 §6）。
 *
 * 按线路取其一：大陆 → 人民币（3% 手续费，收款口径「支付宝号 或 银行卡号，填一个即可」）；
 * 国际 → USDT（固定 1 USDT/次，TRC20 地址）。
 * 金额校验、手续费说明都来自后端字段（`fee_rate` / `fee_fixed`），不写死。
 */
export function WithdrawModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const snapshot = useAccountStore((state) => state.snapshot)
  const withdrawRmb = useAccountStore((state) => state.withdrawRmb)
  const withdrawUsdt = useAccountStore((state) => state.withdrawUsdt)

  const [amount, setAmount] = useState('')
  const [zhifubao, setZhifubao] = useState('')
  const [bank, setBank] = useState('')
  const [trc20, setTrc20] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!snapshot) return null
  const line = snapshot.line?.preferred ?? 'cn'
  const isRmb = line === 'cn'
  const commission = snapshot.commission
  const rmb = commission?.rmb
  const usdt = commission?.usdt
  // 支付宝、银行卡两个都没存过时，才要求本次至少填一个（清单 §5.2）
  const needPayee = rmb ? !(rmb.payee_ready?.zhifubao || rmb.payee_ready?.bank) : false

  const reset = () => {
    setAmount('')
    setZhifubao('')
    setBank('')
    setTrc20('')
    setError('')
  }

  const submit = async () => {
    const value = Number(amount.trim())
    if (!Number.isFinite(value) || value <= 0) {
      setError('请输入有效的提现金额。')
      return
    }
    setBusy(true)
    setError('')
    let result
    if (isRmb) {
      if (needPayee && !zhifubao.trim() && !bank.trim()) {
        setBusy(false)
        setError('请先填写支付宝账号或银行卡号（有一个即可）。')
        return
      }
      result = await withdrawRmb({ amount: value, zhifubao: zhifubao.trim(), bank: bank.trim() })
    } else {
      result = await withdrawUsdt({ amount: value, trc20_address: trc20.trim() })
    }
    setBusy(false)
    if (result === null) {
      setError('界面与主程序之间的通信桥未建立，请重启应用。')
      return
    }
    if (!result.ok) {
      setError(result.error ?? '提现申请失败。')
      return
    }
    reset()
    onClose()
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset()
        onClose()
      }}
      title={isRmb ? '人民币提现' : 'USDT 提现'}
      description={isRmb ? '手续费 3%，按原额扣除后实发净额，提交后等待人工审核。' : '固定手续费 1 USDT/次，提交后等待人工审核。'}
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            提交申请
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="提现金额" hint={isRmb ? `可提现 ¥${rmb?.withdrawable ?? '0.00'}` : `可提现 ${usdt?.withdrawable ?? '0'} USDT`}>
          <Input
            type="number"
            value={amount}
            autoFocus
            autoComplete="off"
            inputMode="decimal"
            onChange={(event) => {
              setAmount(event.target.value)
              setError('')
            }}
            placeholder={isRmb ? '提现金额（元）' : '提现金额（USDT）'}
          />
        </Field>

        {isRmb ? (
          <>
            <Field label="支付宝号" hint={rmb?.payee_ready?.zhifubao ? '已保存，无需重复填写' : '与银行卡号二选一填写'}>
              <Input
                value={zhifubao}
                autoComplete="off"
                onChange={(event) => {
                  setZhifubao(event.target.value)
                  setError('')
                }}
                placeholder="支付宝账号（选填）"
              />
            </Field>
            <Field label="银行卡号" hint={rmb?.payee_ready?.bank ? '已保存，无需重复填写' : '与支付宝号二选一填写'}>
              <Input
                value={bank}
                autoComplete="off"
                onChange={(event) => {
                  setBank(event.target.value)
                  setError('')
                }}
                placeholder="银行卡号（选填）"
              />
            </Field>
            {needPayee ? (
              <p className="text-[11.5px] text-ink-faint">支付宝号 或 银行卡号，填一个即可。</p>
            ) : null}
            {rmb ? (
              <p className="text-[11.5px] text-ink-faint">手续费 {Math.round(rmb.fee_rate * 100)}%，到账为扣费后的净额。</p>
            ) : null}
          </>
        ) : (
          <>
            <Field label="收款地址（TRC20）" hint="T 开头，共 34 位。">
              <Input
                value={trc20}
                autoComplete="off"
                spellCheck={false}
                onChange={(event) => {
                  setTrc20(event.target.value)
                  setError('')
                }}
                placeholder="T 开头的 TRC20 地址"
              />
            </Field>
            {usdt ? <p className="text-[11.5px] text-ink-faint">固定手续费 {usdt.fee_fixed} USDT/次，到账为扣费后的净额。</p> : null}
          </>
        )}

        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
