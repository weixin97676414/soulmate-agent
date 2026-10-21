import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'







export function PasswordModal({
  open,
  onClose,
  hasPassword,
}: {
  open: boolean
  onClose: () => void
  hasPassword: boolean
}) {
  const setPassword = useAccountStore((state) => state.setPassword)
  const [next, setNext] = useState('')
  const [old, setOld] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setNext('')
    setOld('')
    setError('')
  }

  const submit = async () => {
    if (next.length < 6) {
      setError('密码至少 6 位。')
      return
    }
    if (hasPassword && !old) {
      setError('请输入旧密码。')
      return
    }
    setBusy(true)
    setError('')
    const result = await setPassword(next, old)
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
      title={hasPassword ? '修改密码' : '设置密码'}
      
      
      
      description="账号密码用于开源社区登录、参与活动与交流。设置后请妥善保管。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            {hasPassword ? '修改' : '设置'}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="新密码">
          <Input
            type="password"
            value={next}
            autoFocus
            autoComplete="new-password"
            onChange={(event) => {
              setNext(event.target.value)
              setError('')
            }}
            placeholder="至少 6 位"
          />
        </Field>
        {hasPassword ? (
          <Field label="旧密码">
            <Input
              type="password"
              value={old}
              autoComplete="current-password"
              onChange={(event) => {
                setOld(event.target.value)
                setError('')
              }}
              placeholder="当前密码"
            />
          </Field>
        ) : null}
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
