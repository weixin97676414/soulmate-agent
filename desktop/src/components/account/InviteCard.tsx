import { useState } from 'react'
import { Check, Copy, Gift } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { InviteModal } from '@/components/account/InviteModal'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'
import { copyText } from '@/utils/amount'







export function InviteCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  if (!snapshot) return null
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current

  const copyInvite = async () => {
    if (!current?.my_invite_code) return
    if (await copyText(current.my_invite_code)) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    
    
    <Card title="邀请朋友加入社区">
      {




}
      <p className="mb-2.5 text-[12.5px] leading-relaxed text-ink-soft">
        官方邀请码 <b className="font-semibold text-ink">XJX</b>，填写可获得 20 Token
      </p>
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">登录账号后即可查看邀请码。</p>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[11.5px] text-ink-faint">我的邀请码</div>
              <div className="selectable text-[20px] font-semibold tracking-[0.08em] text-ink">
                {current.my_invite_code}
              </div>
            </div>
            <Button
              size="sm"
              icon={copied ? <Check size={13} /> : <Copy size={13} />}
              onClick={() => void copyInvite()}
              disabled={!current.my_invite_code}
            >
              {copied ? '已复制' : '复制'}
            </Button>
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-line-soft pt-3">
            {current.invite_bound ? (
              






              <span className="text-[12.5px] leading-relaxed text-ink-soft">
                你受
                {current.inviter_masked ? (
                  <span className="mx-1 font-medium text-ink">{current.inviter_masked}</span>
                ) : null}
                邀请加入社区，感谢你们为社区建设做出的贡献。
              </span>
            ) : (
              <span className="min-w-0 flex-1 text-[12.5px] leading-relaxed text-ink-soft">
                每邀请一位朋友加入社区，你可获得 10 Token，填朋友邀请码可获得 30 Token。
              </span>
            )}
            {!current.invite_bound ? (
              <Button
                size="sm"
                variant="secondary"
                icon={<Gift size={13} />}
                disabled={disabled}
                onClick={() => setOpen(true)}
              >
                填写邀请码
              </Button>
            ) : (
              <Badge tone="success">已绑定</Badge>
            )}
          </div>
        </div>
      )}
      <InviteModal open={open} onClose={() => setOpen(false)} />
    </Card>
  )
}
