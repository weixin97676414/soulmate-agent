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

/**
 * 任务计划卡片 —— 单聊里"AI 先把打算怎么做摆出来、等你点头"的那张卡片。
 *
 * 存在的意义是**把看不见的编排变成看得见、可干预的东西**：普通聊天客户端里
 * 模型内部有多少步骤、做到哪了，用户完全无从知晓；这里把目标、步骤清单、
 * 进度与失败原因都摊开，还能在执行前改一版计划。
 *
 * 视觉与「工具调用卡片」保持一致（圆角、细边框、可折叠、悬停反馈），
 * 让用户一眼认出"这是 AI 在汇报它的做事安排"，而不是另一套陌生的控件。
 */
export function PlanCard({
  plan,
  /**
   * 隐藏自带的标题行与进度行。
   *
   * 给「任务执行计划」条用（`PlanBar`）：那一层已经有自己的标题与进度条，
   * 这里再画一遍就是同一句话说两次。**明细部分（目标 / 步骤 / 三个操作按钮）
   * 两边共用**，所以只有这个开关，没有第二份渲染代码。
   */
  hideHeader = false,
}: {
  plan: Plan
  hideHeader?: boolean
}) {
  // 等待确认时需要显眼（用户要在这里做决定），执行与结束后默认收起，
  // 免得一次次出现的卡片把正文挤得太远 —— 折叠后仍能看到进度那行。
  const [open, setOpen] = useState(plan.state === 'awaiting')

  /**
   * 实际是否渲染明细。**`hideHeader` 时恒为 `true`**。
   *
   * ⚠️ 这是修一个真实 bug（报："收起之后就无法再展开了，
   * 独立窗口中也无法展开"）。
   *
   * ## 病根是**两层折叠**
   *
   * `PlanBar` 自己有一份展开态（它控制"渲不渲染 `<PlanCard>`"），而 `PlanCard`
   * 又有一份（上面那个 `open`）。平时相安无事，出事在**卸载重挂**那一下：
   *
   *   ① 计划是 `awaiting` → 用户点开过明细 → `PlanCard.open = true`；
   *   ② 用户收起 `PlanBar` → `<PlanCard>` **被卸载**（连同它的 `open` 一起丢）；
   *   ③ 期间点了「开始执行」，`plan.state` 变成 `executing`；
   *   ④ 用户再点展开 → `<PlanCard>` **重新挂载** → `open` 初始值 =
   *      `('executing' === 'awaiting')` = **false** → 明细不渲染；
   *   ⑤ 而打开它的那个 `<button>` 在 `!hideHeader` 的分支里，`PlanBar` 传的
   *      正是 `hideHeader` —— **没有任何按钮能把它打开**。
   *
   * 结果是"展开后一片空白"，而且越点越像坏了（外面那层确实在开合，
   * 只是里面永远空着）。
   *
   * ## 修法：谁管展开态，就只让谁管
   *
   * `hideHeader` 的语义本来就是"外层（`PlanBar`）负责标题与展开"，所以这里
   * 不该再叠一层。恒展开之后，`PlanBar` 的收起/展开就是**唯一**的那一层。
   *
   * ⚠️ 反过来，`!hideHeader`（渲染在消息里那种独立卡片）**必须保留**自己的
   * `open` —— 那里没有外层，标题行那个按钮就是唯一的开合入口。
   */
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

  // ---- 语音 ----
  //
  // 三个动作各自登记，且**只在"这一刻真的能点"时才登记**（`voiceable`）：
  // 计划已经在执行、或正在改的时候，说「开始执行」不该有任何反应。
  // 传 `null` 表示"此刻不提供" —— 比放一个点了没反应的函数诚实得多，
  // 那种"界面说它有、实际不动"是最让人困惑的失败。
  const voiceable = awaiting && !busy && !revising
  useVoiceCommand('plan.approve', voiceable ? () => void submit(true) : null)
  useVoiceCommand('plan.revise', voiceable ? () => setRevising(true) : null)
  useVoiceCommand('plan.abort', voiceable ? () => void submit(false) : null)

  const submit = async (approved: boolean, text = ''): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      // 把自己的 `plan.id` 一并回传：store 不再去消息列表里反查
      // （消息按会话分桶后，反查会跨会话找错那一版计划）
      await respondPlan(plan.id, approved, text)
      // 「改一下」提交后收起输入框：重拟的新计划会以新的一版卡片状态回来，
      // 老输入框留着只会让人以为"点了没反应"。
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
        // `hideHeader` 时它只是「任务执行计划」条内部的一块，不该再带外边距和
        // 自己的圆角边框（那会形成"框里套框"）
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
          {/* 标题行 */}
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

          {/* 进度行：折叠时也保留 —— 这是"做到哪了"最快的答案 */}
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
                        /*
                          ⚠️ 完成的那一步**画删除线**（产品要求
                          "逐个打勾完成划线删除"）。

                          这里原先是"降透明度 + 变浅灰"，注释里给的理由是
                          "删除线在多步清单里糊成一片"。那条判断**被用户推翻了**：
                          变灰只是"看起来弱一点"，而划掉是"这件事**已经结了**" ——
                          一份正在跑的清单里，用户需要一眼分清"哪几步不用再管了"。

                          ⚠️ 所以**不再叠加 `opacity-70`**：透明度会把删除线本身
                          也一起变淡，划痕细到几乎看不见，等于白划。要弱就靠
                          `text-ink-faint` 那一层，够了。
                        */
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

          {/* 操作区：**只在等待确认时出现** —— 执行中/结束后再给按钮会误导 */}
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
