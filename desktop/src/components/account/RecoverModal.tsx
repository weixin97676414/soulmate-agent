import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'








export function RecoverModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const recover = useAccountStore((state) => state.recover)
  const [account, setAccount] = useState('')
  const [next, setNext] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [manualReset, setManualReset] = useState<{ email: string; require: string } | null>(null)

  const reset = () => {
    setAccount('')
    setNext('')
    setError('')
    setManualReset(null)
  }

  const submit = async () => {
    if (!account.trim() || next.length < 6) {
      setError('请输入账号，并设置一个至少 6 位的新密码。')
      return
    }
    setBusy(true)
    setError('')
    setManualReset(null)
    const result = await recover(account.trim(), next)
    setBusy(false)
    if (result === null) {
      setError('界面与主程序之间的通信桥未建立，请重启应用。')
      return
    }
    if (!result.ok) {
      setError(result.error ?? '重置失败。')
      if (result.manualReset) setManualReset(result.manualReset)
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
      title="忘记密码"
      description="用本机设备身份重置这个账号的密码（只对本机绑定过的账号有效）。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            重置密码
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="账号">
          <Input
            value={account}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => {
              setAccount(event.target.value)
              setError('')
            }}
            placeholder="xjx…"
          />
        </Field>
        <Field label="新密码">
          <Input
            type="password"
            value={next}
            autoComplete="new-password"
            onChange={(event) => {
              setNext(event.target.value)
              setError('')
            }}
            placeholder="至少 6 位"
          />
        </Field>
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
        {manualReset ? (
          <div className="rounded-[8px] border border-warning/30 bg-warning-soft px-3 py-2.5 text-[12px] leading-relaxed text-ink-soft">
            <p className="font-medium text-warning">自动重置未通过</p>
            <p className="mt-1">
              请把材料发送到 <span className="selectable font-medium text-ink">{manualReset.email}</span>：
            </p>
            <p className="selectable mt-0.5">{manualReset.require}</p>
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
