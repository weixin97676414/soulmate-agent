


















import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { ChevronRight, ListChecks } from 'lucide-react'

import { PlanCard } from '@/components/chat/PlanCard'
import type { ChatMessage, Plan } from '@/types'


function latestPlan(messages: ChatMessage[]): Plan | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const plan = messages[i]?.plan
    if (plan) return plan
  }
  return null
}

export function PlanBar({ messages }: { messages: ChatMessage[] }) {
  const plan = latestPlan(messages)
  const [open, setOpen] = useState(true)
  const [seenId, setSeenId] = useState('')

  











  useEffect(() => {
    if (!plan) return
    if (plan.id === seenId) return
    setSeenId(plan.id)
    setOpen(true)
  }, [plan, plan?.id, seenId])

  if (!plan) return null

  const total = plan.steps.length
  const finished = plan.steps.filter(
    (step) => step.status === 'done' || step.status === 'failed',
  ).length
  const ratio = total === 0 ? 0 : finished / total

  return (
    <div className="shrink-0 overflow-hidden rounded-[12px] border border-line bg-panel">
      {


}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-hover"
      >
        <ChevronRight
          size={13}
          className={clsx(
            'shrink-0 text-ink-faint transition-transform',
            open ? 'rotate-90' : '',
          )}
        />
        <ListChecks size={13} className="shrink-0 text-brand" />
        <span className="shrink-0 text-[12px] font-medium text-ink">任务执行计划</span>

        {}
        <span className="ml-1 h-1 min-w-[60px] flex-1 overflow-hidden rounded-full bg-canvas">
          <span
            className="block h-full rounded-full bg-brand transition-[width] duration-300"
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </span>
        <span className="shrink-0 text-[11px] text-ink-faint">
          {finished}/{total}
        </span>
      </button>

      {open ? (
        
        
        
        
        <PlanCard plan={plan} hideHeader />
      ) : null}
    </div>
  )
}
