import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 补填邀请码（文档 §5.12 + §5.2）。
 *
 * 只可补一次：填官方码 `XJX` 得 20 token，填其他有效码得 30 token。
 * 按文档 §5.2，输入框**默认填官方码 XJX** 并明确说明（不能只是默默填上）。
 */
export function InviteModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const invite = useAccountStore((state) => state.invite)
  const [code, setCode] = useState('XJX')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setCode('XJX')
    setError('')
  }

  const submit = async () => {
    if (!code.trim()) {
      setError('请输入邀请码。')
      return
    }
    setBusy(true)
    setError('')
    const result = await invite(code.trim())
    setBusy(false)
    if (result === null) {
      setError('界面与主程序之间的通信桥未建立，请重启应用。')
      return
    }
    if (!result.ok) {
      setError(result.error ?? '操作失败。')
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
      title="填写邀请码"
      description="填官方码（XJX）得 20 Token，填其他有效邀请码得 30 Token，只能补一次。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>稍后再说</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            提交
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field
          label="邀请码"
          hint="已默认填入官方码（XJX），可获 +20 Token。若你有好友的邀请码，替换填写可得 +30 Token。"
        >
          <Input
            value={code}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => {
              setCode(event.target.value)
              setError('')
            }}
            placeholder="邀请码"
          />
        </Field>
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
