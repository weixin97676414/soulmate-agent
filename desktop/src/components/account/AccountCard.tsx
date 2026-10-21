import { useState } from 'react'
import { UserRoundPen } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { RenameModal } from '@/components/account/RenameModal'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'












export function AccountCard() {
  const snapshot = useAccountStore((state) => state.snapshot)

  const [renameOpen, setRenameOpen] = useState(false)

  if (!snapshot) return null

  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable

  return (
    
    
    <Card title="社区账号">
      {!snapshot.deviceUsable ? (
        <p className="text-[12.5px] leading-relaxed text-danger">
          无法识别本机设备，账号相关功能暂不可用。
        </p>
      ) : !current ? (
        <p className="text-[12.5px] leading-relaxed text-ink-soft">
          {snapshot.offline
            ? '当前未联网，还拿不到本机账号；联网后会自动补齐。'
            : '正在为本机准备账号…'}
        </p>
      ) : (
        <div className="flex items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="truncate text-[22px] font-semibold tracking-tight text-ink">
              {current.account}
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              {current.is_primary ? <Badge tone="brand">本机账号</Badge> : null}
              <Badge tone="neutral">{current.has_password ? '已设密码' : '未设密码'}</Badge>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            icon={<UserRoundPen size={13} />}
            disabled={disabled}
            onClick={() => setRenameOpen(true)}
          >
            修改账号名
          </Button>
        </div>
      )}

      <RenameModal
        open={renameOpen}
        onClose={() => setRenameOpen(false)}
        hasPassword={current?.has_password ?? false}
      />
    </Card>
  )
}
