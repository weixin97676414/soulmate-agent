import clsx from 'clsx'
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  ListChecks,
  Loader2,
  Pencil,
  Play,
  X,
  XCircle,
} from 'lucide-react'
import { useState } from 'react'

import { Badge, Button, Textarea } from '@/components/ui'
import { useChatStore } from '@/stores/chatStore'
import { useVoiceCommand } from '@/stores/voiceCommandStore'
import type { Plan, PlanState, PlanStepStatus } from '@/types'

const STATE_META: Record<
  PlanState,
  { tone: 'neutral' | 'brand' | 'success' | 'warning' | 'danger'; label: string }
> = {
  awaiting: { tone: 'warning', label: '等待确认' },
  executing: { tone: 'brand', label: '执行中' },
  done: { tone: 'success', label: '已完成' },
  cancelled: { tone: 'neutral', label: '已取消' },
  aborted: { tone: 'neutral', label: '已取消' },
}

const STEP_META: Record<
  PlanStepStatus,
  { icon: typeof Circle; className: string; spinning?: boolean }
> = {
  pending: { icon: Circle, className: 'text-ink-faint' },
  doing: { icon: Loader2, className: 'text-brand', spinning: true },
  done: { icon: CheckCircle2, className: 'text-success' },
  failed: { icon: XCircle, className: 'text-danger' },
}











export function PlanCard({
  plan,
  






  hideHeader = false,
}: {
  plan: Plan
  hideHeader?: boolean
}) {
  
  
  const [open, setOpen] = useState(plan.state === 'awaiting')

  





























  const expanded = hideHeader || open
  const [revising, setRevising] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [busy, setBusy] = useState(false)

  const respondPlan = useChatStore((state) => state.respondPlan)

  const meta = STATE_META[plan.state] ?? STATE_META.awaiting
  const total = plan.steps.length
  const finished = plan.steps.filter(
    (step) => step.status === 'done' || step.status === 'failed',
  ).length
  const ratio = total === 0 ? 0 : finished / total
  const awaiting = plan.state === 'awaiting'

  
  
  
  
  
  
  const voiceable = awaiting && !busy && !revising
  useVoiceCommand('plan.approve', voiceable ? () => void submit(true) : null)
  useVoiceCommand('plan.revise', voiceable ? () => setRevising(true) : null)
  useVoiceCommand('plan.abort', voiceable ? () => void submit(false) : null)

  const submit = async (approved: boolean, text = ''): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      
      
      await respondPlan(plan.id, approved, text)
      
      
      if (!approved) {
        setRevising(false)
        setFeedback('')
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      className={clsx(
        
        
        hideHeader
          ? 'overflow-hidden'
          : 'animate-enter my-2 overflow-hidden rounded-[10px] border bg-canvas transition-colors',
        !hideHeader &&
          (plan.state === 'awaiting'
            ? 'border-brand/30'
            : plan.state === 'done'
              ? 'border-success/25'
              : plan.state === 'executing'
                ? 'border-brand/20'
                : 'border-line'),
      )}
    >
      {!hideHeader ? (
        <>
          {}
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="no-drag flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-hover"
          >
            <ChevronRight
              size={13}
              className={clsx('shrink-0 text-ink-faint transition-transform', open && 'rotate-90')}
            />
            <ListChecks size={13} className="shrink-0 text-ink-faint" />
            <span className="shrink-0 text-[12.5px] font-medium text-ink">任务计划</span>
            {awaiting ? (
              <span className="shrink-0 text-[11.5px] text-ink-faint">· 等你确认后再动手</span>
            ) : null}

            <span className="min-w-0 flex-1" />

            <Badge tone={meta.tone} className="shrink-0">
              {meta.label}
            </Badge>
          </button>

          {}
          <div className="flex items-center gap-2 px-3 pb-2">
            <div className="h-[4px] min-w-0 flex-1 overflow-hidden rounded-full bg-panel">
              <div
                className={clsx(
                  'h-full rounded-full transition-[width] duration-500 ease-out',
                  plan.steps.some((step) => step.status === 'failed')
                    ? 'bg-danger/70'
                    : 'bg-brand',
                )}
                style={{ width: `${Math.round(ratio * 100)}%` }}
              />
            </div>
            <span className="shrink-0 text-[11px] text-ink-faint">
              {finished}/{total} 已完成
            </span>
          </div>
        </>
      ) : null}

      {expanded ? (
        <div className="border-t border-line-soft px-3 py-2.5">
          {plan.goal ? (
            <p className="selectable mb-2.5 text-[12px] leading-relaxed text-ink-soft">
              {plan.goal}
            </p>
          ) : null}

          <ol className="flex flex-col gap-1.5">
            {plan.steps.map((step) => {
              const stepMeta = STEP_META[step.status] ?? STEP_META.pending
              const Icon = stepMeta.icon
              const settled = step.status === 'done'
              return (
                <li key={step.id} className="flex items-start gap-2">
                  <Icon
                    size={13}
                    className={clsx(
                      'mt-[3px] shrink-0 transition-colors',
                      stepMeta.className,
                      stepMeta.spinning && 'animate-spin',
                    )}
                  />
                  <div className="min-w-0 flex-1">
                    <span
                      className={clsx(
                        'selectable text-[12.5px] leading-relaxed',
                        settled ? 'text-ink-faint' : 'text-ink',
                        step.status === 'failed' && 'text-danger',
                        












                        settled && 'line-through',
                      )}
                    >
                      <span className="mr-1 text-[11px] text-ink-faint">{step.id}.</span>
                      {step.text}
                    </span>
                    {step.note ? (
                      <p
                        className={clsx(
                          'mt-0.5 text-[11.5px] leading-relaxed',
                          step.status === 'failed' ? 'text-danger/85' : 'text-ink-faint',
                        )}
                      >
                        {step.note}
                      </p>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>

          {}
          {awaiting ? (
            <div className="mt-3 border-t border-line-soft pt-2.5">
              {revising ? (
                <div className="flex flex-col gap-2">
                  <Textarea
                    value={feedback}
                    onChange={(event) => setFeedback(event.target.value)}
                    rows={2}
                    autoFocus
                    placeholder="说说哪里想改，例如：第 2 步改成用表格呈现"
                    className="text-[12.5px]"
                  />
                  <div className="flex items-center gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      icon={<Check size={13} />}
                      disabled={busy || !feedback.trim()}
                      onClick={() => void submit(false, feedback)}
                    >
                      重新拟计划
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => {
                        setRevising(false)
                        setFeedback('')
                      }}
                    >
                      取消
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Play size={13} />}
                    disabled={busy}
                    onClick={() => void submit(true)}
                  >
                    开始执行
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Pencil size={13} />}
                    disabled={busy}
                    onClick={() => setRevising(true)}
                  >
                    改一下
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={<X size={13} />}
                    disabled={busy}
                    onClick={() => void submit(false)}
                  >
                    不用了
                  </Button>
                </div>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
