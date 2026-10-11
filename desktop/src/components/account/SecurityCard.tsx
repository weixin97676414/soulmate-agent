import { useState } from 'react'
import { KeyRound, LockKeyhole } from 'lucide-react'

import { Card } from '@/components/account/Card'
import { PasswordModal } from '@/components/account/PasswordModal'
import { RecoverModal } from '@/components/account/RecoverModal'
import { ReloginModal } from '@/components/account/ReloginModal'
import { Badge, Button } from '@/components/ui'
import { useAccountStore } from '@/stores/accountStore'

/**
 * 密码与安全卡：设 / 改密码、忘记密码。
 *
 * ⚠️ 这个功能的用途被**收窄过两次**，卡片文案必须跟着说清：
 *
 * 1. 本应用**不支持在别的设备登录**（设备与账号一对一绑定，
 *    见 `AccountCard` 的说明）。原文案写的是"要在别的设备登录就必须先设一个密码"
 *    —— 那会让人以为本应用能多设备登录，是把用户往一个不存在的功能上引。
 * 2. （产品约定）用途表述改成 **"账号密码用于开源社区登录、
 *    参与活动与交流"**。原先只写"在官网登录后获取 / 导入搭子与技能组" ——
 *    那只是其中一个用途，而用户实际在做的事（在社区里参与活动、和人交流）
 *    一个都没提，读起来像"设密码只为了导东西"。
 *
 * "未设密码"依然**不是错误**：本机自动创建的账号本来就是无密码起步（文档 §0），
 * 本机使用完全不需要它；需要密码的只有"要去社区 / 官网登录"这件事。
 */
export function SecurityCard() {
  const snapshot = useAccountStore((state) => state.snapshot)
  const [passwordOpen, setPasswordOpen] = useState(false)
  const [recoverOpen, setRecoverOpen] = useState(false)
  const [reloginOpen, setReloginOpen] = useState(false)

  if (!snapshot) return null
  const current = snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null
  const disabled = snapshot.offline || !snapshot.deviceUsable || !current
  /**
   * 本机设备凭据缺失（且有账号）→ 返佣、钱包这些要设备签名的数据暂时读不到。
   *
   * 起改为**静默自动愈合**：主进程在首启与登录后都会自动尝试补回
   * `device_secret`（无密码主账号会静默默认登录后补发，见 engine 的 healDeviceKeyIfMissing）。
   * 所以这里**不再弹醒目警告**，只留一行不打扰的小字：愈合成功后它会随快照自动消失；
   * 只剩"有密码、没法静默补"的账号才保留一个轻量的密码登录入口。
   */
  const needsRelogin = Boolean(current) && !snapshot.hasDeviceSecret

  return (
    <Card
      title="密码与安全"
      actions={
        // 未设密码用中性色而不是警告色：本机使用根本不需要它（见文件头的说明），
        // 标成警告会让人以为"我这账号不安全"，而事实恰恰相反 —— 密码只给官网用
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
            {/* ：两句里的"导出 / 导入"统一改成"获取 / 导入"（与权益页同一口径）——
                "获取"才说得清方向：搭子与技能组在官网上，这里的动作是把它拿回本机 */}
            {/* ⚠️ 口径 更新为"开源社区登录、参与活动与交流"：
                原先写的"在官网登录后获取 / 导入搭子与技能组"太窄 —— 那只是
                其中一个用途，而用户实际的用法（在社区里参与活动、和人交流）
                一个都没提到，读起来像"设密码只为了导东西"。 */}
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
