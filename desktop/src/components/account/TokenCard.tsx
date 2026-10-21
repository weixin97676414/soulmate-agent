import { Card } from '@/components/account/Card'
import { useAccountStore } from '@/stores/accountStore'
import { formatToken } from '@/utils/amount'




























export function TokenCard() {
  const snapshot = useAccountStore((state) => state.snapshot)

  if (!snapshot) return null
  const current =
    snapshot.accounts.find((item) => item.id === snapshot.currentId) ?? snapshot.accounts[0] ?? null

  return (
    








    <Card
      
      
      title="我的 Token（社区贡献值）"
    >
      {!current ? (
        <p className="text-[12.5px] text-ink-soft">账号就绪后即可查看 Token 余额。</p>
      ) : (
        <div className="space-y-2">
          <div className="flex items-end gap-2">
            <span className="text-[22px] font-semibold leading-none tracking-tight text-ink tabular-nums">
              {formatToken(current.token_balance)}
            </span>
            {





}
            <span className="pb-0.5 text-[12.5px] text-ink-soft">Token</span>
          </div>
          {

}
          <p className="text-[13px] font-medium leading-relaxed text-ink-soft">
            Token 是 Soulmate Agent 开源社区的<b className="text-ink-soft">贡献值</b>，
            在社区里用它记录你的贡献。
          </p>
        </div>
      )}
    </Card>
  )
}
