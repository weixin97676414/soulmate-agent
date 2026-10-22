import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'







export function LoginModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const login = useAccountStore((state) => state.login)
  const [account, setAccount] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const reset = () => {
    setAccount('')
    setPassword('')
    setError('')
  }

  const submit = async () => {
    if (!account.trim() || !password) {
      setError('请输入账号与密码。')
      return
    }
    setBusy(true)
    setError('')
    const result = await login(account.trim(), password)
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
      title="登录其他账号"
      description="用账号 + 密码登录一个已存在的账号，登录后它也会加入本机的账号列表。"
      width="max-w-md"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" icon={busy ? <Spinner /> : undefined} disabled={busy} onClick={() => void submit()}>
            登录
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="账号" hint="就是形如 xjx… 的那个账号名。">
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
        <Field label="密码" hint="该账号在它的绑定设备上设置过的密码。">
          <Input
            type="password"
            value={password}
            autoComplete="off"
            onChange={(event) => {
              setPassword(event.target.value)
              setError('')
            }}
            placeholder="账号密码"
          />
        </Field>
        {error ? <p className="text-[12.5px] text-danger">{error}</p> : null}
      </div>
    </Modal>
  )
}
