import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'






export function RenameModal({
  open,
  onClose,
  hasPassword,
}: {
  open: boolean
  onClose: () => void
  hasPassword: boolean
}) {
  const rename = useAccountStore((state) => state.rename)
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setName('')
    setPassword('')
    setError('')
  }

  const submit = async () => {
    if (!/^[A-Za-z0-9_]{3,32}$/.test(name.trim())) {
      setError('账号名必须是 3–32 位字母、数字或下划线。')
      return
    }
    if (hasPassword && !password) {
      setError('请输入当前账号的密码。')
      return
    }
    setBusy(true)
    setError('')
    const result = await rename(name.trim(), password)
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
      title="修改账号名"
      description="账号名是你登录时的身份，改完后请用新名字登录。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="新账号名">
          <Input
            value={name}
            autoFocus
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => {
              setName(event.target.value)
              setError('')
            }}
            placeholder="3–32 位字母、数字或下划线"
          />
        </Field>
        {hasPassword ? (
          <Field label="当前密码">
            <Input
              type="password"
              value={password}
              autoComplete="current-password"
              onChange={(event) => {
                setPassword(event.target.value)
                setError('')
              }}
              placeholder="用于确认是你本人在操作"
            />
          </Field>
        ) : null}
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
