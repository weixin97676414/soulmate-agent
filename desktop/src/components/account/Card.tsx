import type { ReactNode } from 'react'








export function Card({
  title,
  actions,
  flash,
  children,
}: {
  title: string
  actions?: ReactNode
  





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


export function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <span className="shrink-0 text-[12.5px] text-ink-soft">{label}</span>
      <span className="min-w-0 text-right text-[12.5px] text-ink">{children}</span>
    </div>
  )
}
