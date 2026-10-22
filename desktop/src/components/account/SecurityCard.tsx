import { useState } from 'react'
import { KeyRound, LockKeyhole } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { PasswordModal } from '@/components/account/PasswordModal'
import { RecoverModal } from '@/components/account/RecoverModal'
import { ReloginModal } from '@/components/account/ReloginModal'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

















export function SecurityCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [recoverOpen, setRecoverOpen] = useState(false)
  const [reloginOpen, setReloginOpen] = useState(false)

  if (!snapshot) return null
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current
  







  const needsRelogin = Boolean(current) && !snapshot.hasDeviceSecret

  return (
    <Card
      title="密码与安全"
      actions={
        
        
        <Badge tone={current?.has_password ? 'success' : 'neutral'}>
          {current ? (current.has_password ? '已设置' : '未设置') : '——'}
        </Badge>
      }
    >
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">账号准备好后即可在这里管理密码。</p>
      ) : (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            {
}
            {


}
            <p className="text-[12.5px] leading-relaxed text-ink-soft">
              {current.has_password
                ? '密码已设置。账号密码用于开源社区登录、参与活动与交流。'
                : '这个账号目前没有密码，本机使用不需要密码。要在开源社区登录、参与活动与交流时，才需要设置一个。'}
            </p>
            <p className="mt-1 text-[11.5px] leading-relaxed text-ink-faint">
              本应用不支持在其它设备登录：账号与本机是一对一绑定的。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              icon={current.has_password ? <KeyRound size={13} /> : <LockKeyhole size={13} />}
              disabled={disabled}
              onClick={() => setPasswordOpen(true)}
            >
              {current.has_password ? '修改密码' : '设置密码'}
            </Button>
            <Button size="sm" variant="ghost" disabled={disabled} onClick={() => setRecoverOpen(true)}>
              忘记密码
            </Button>
          </div>
        </div>
      )}
      {needsRelogin ? (
        <p className="mt-3 text-[11.5px] leading-relaxed text-ink-faint">
          返佣、钱包等需要设备签名才能读取的数据暂不可用（本机设备凭据需重新确认）。
          {current?.has_password ? (
            <>
              {' '}
              如一直未恢复，可
              <button
                type="button"
                className="mx-0.5 text-brand underline"
                onClick={() => setReloginOpen(true)}
              >
                用密码登录
              </button>
              恢复。
            </>
          ) : (
            ' 应用会尝试自动恢复。'
          )}
        </p>
      ) : null}
      <PasswordModal open={passwordOpen} onClose={() => setPasswordOpen(false)} hasPassword={current?.has_password ?? false} />
      <RecoverModal open={recoverOpen} onClose={() => setRecoverOpen(false)} />
      <ReloginModal
        open={reloginOpen}
        onClose={() => setReloginOpen(false)}
        account={current?.account ?? ''}
      />
    </Card>
  )
}
