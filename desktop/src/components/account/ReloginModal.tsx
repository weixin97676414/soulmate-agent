import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'





















export function ReloginModal({
  open,
  onClose,
  account,
}: {
  open: boolean
  onClose: () => void
  
  account: string
}) {
  const login = useAccountStore((state) => state.login)
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setPassword('')
    setError('')
  }

  const submit = async () => {
    if (!password) {
      setError('请输入这个账号的密码。')
      return
    }
    setBusy(true)
    setError('')
    const result = await login(account, password)
    setBusy(false)
    if (result === null) {
      setError('界面与主程序之间的通信桥未建立，请重启应用。')
      return
    }
    if (!result.ok) {
      setError(result.error ?? '登录失败。')
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
      title="恢复本机凭据"
      description="用这个账号的密码登录一次，之后返佣与钱包数据就能正常读取。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button
            variant="primary"
            icon={busy ? <Spinner /> : undefined}
            disabled={busy}
            onClick={() => void submit()}
          >
            登录
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="账号" hint="本机绑定的账号，不可修改">
          <Input value={account} readOnly spellCheck={false} autoComplete="off" />
        </Field>
        <Field label="密码" hint="没有密码就先点「忘记密码」设一个，再回来登录">
          <Input
            type="password"
            value={password}
            autoFocus
            autoComplete="current-password"
            onChange={(event) => {
              setPassword(event.target.value)
              setError('')
            }}
            placeholder="这是你为官网登录设置的那个密码"
          />
        </Field>
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
