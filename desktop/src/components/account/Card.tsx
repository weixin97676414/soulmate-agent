import type { ReactNode } from 'react'

/**
 * 权益页里各区块的卡片外壳。
 *
 * 单独抽出来是因为五个卡片要**长得一模一样**：标题字号、内边距、圆角、边框
 * 任何一处各自为政，用户扫过去就会觉得"这一页拼凑感很重"。与设置页的卡片
 * 用同一套令牌（`panel` / `line` / `radius-card`），换肤与暗色自动生效。
 */
export function Card({
  title,
  actions,
  flash,
  children,
}: {
  title: string
  actions?: ReactNode
  /**
   * 短暂把整卡边框/底色切成 success（充值到账用）。
   *
   * 复刻 `WalletCard` 的"到账闪一下"：充值是这张卡唯一"钱变了"的时刻，
   * 用户此时视线往往在别处，必须在卡片本身上给一个抓得住的信号。
   */
  flash?: boolean
  children: ReactNode
}) {
  return (
    <section
      className={
        'rounded-[10px] border bg-panel p-4 transition-colors ' +
        (flash ? 'border-success/40 bg-success-soft' : 'border-line')
      }
    >
      <header className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[13.5px] font-medium text-ink">{title}</h3>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </header>
      {children}
    </section>
  )
}

/** 一行「标签 + 值」的说明条目，供卡片内部排版。 */
export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="shrink-0 text-[12.5px] text-ink-soft">{label}</span>
      <span className="min-w-0 text-right text-[12.5px] text-ink">{children}</span>
    </div>
  )
}
