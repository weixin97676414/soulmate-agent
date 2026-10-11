import { useState } from 'react'

import { Button, Field, Input, Modal, Spinner } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 「恢复本机凭据」：用账号 + 密码登录一次，换一个会话 token（文档 §5.5）。
 *
 * ## 为什么需要它
 *
 * 设备凭据（`device_secret`）**只在注册响应里出现过一次**，丢了就换不回来（文档 §4.2）：
 * 换 Windows 用户、重装系统、清空过数据目录、DPAPI 解不开旧密文，都会走到这个状态。
 * 而设备在后端仍有账号，`lookup` 有结果 → 客户端不会再"注册"一次 → secret 永远拿不回来。
 * 后果是所有**需要设备签名**的接口（返佣、钱包）全都失败，界面上却只有一个
 * "缺少设备凭据" —— 用户不知道该做什么（他反馈的原话就是问这句话是什么意思）。
 *
 * 文档给出的补救路径就是这条：**用账号 + 密码登录**（§5.5），拿到 session token 之后
 * token 路径优先于设备签名，那些接口就都活了。没设过密码的话，先走「忘记密码」（§5.11，
 * 只靠账号 + 本机设备指纹，不需要 secret）设一个再回来。
 *
 * ## 它不是"登录别的账号"
 *
 * 账号是**只读的当前账号**（不从输入框取），用户只需要填密码 —— 与"设备与账号一对一绑定、
 * 界面上不该有『登录其他账号』"那条产品约束不冲突：这里做的是**恢复本机凭据**。
 */
export function ReloginModal({
  open,
  onClose,
  account,
}: {
  open: boolean
  onClose: () => void
  /** 当前账号名（只读展示；不从界面取值） */
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
