import { useState } from 'react'
import { UserRoundPen } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { RenameModal } from '@/components/account/RenameModal'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 账号卡：当前账号 + 修改账号名。
 *
 * **这里刻意没有「登录其他账号」与「切换账号」**：设备与账号是一对一绑定的
 * （首启自动创建，创建失败时由权益页顶部「重试」重新查号/重建），产品上不存在
 * "一台设备多个账号"的场景，留着切换器只会让人误以为可以换号。
 * 同理**也没有「在其它设备登录」**：这个账号只在本机用（用户明确口径）。
 *
 * 徽标里的"未设密码"是中性信息而不是警告：密码只给**官网**用（获取 / 导入搭子与
 * 技能组，见 SecurityCard），本机使用不需要它，标成黄色会让人误以为账号不安全。
 */
export function AccountCard() {
  const snapshot = useAccountStore((state) => state.snapshot)

  const [renameOpen, setRenameOpen] = useState(false)

  if (!snapshot) return null

  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable

  return (
    // 「账号」→「社区账号」：与"Token 是社区贡献值""邀请朋友
    // 加入社区"同一套口径 —— 这个账号属于**社区**，不只是本机的一个标识。
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
