/**
 * 「任务执行计划」条 —— 独立于聊天气泡的一块，夹在对话栏与输入栏之间。
 *
 * ## 为什么从消息里搬出来（产品要求）
 *
 * 计划卡片原先渲染在**它那条助手消息内部**（`MessageItem` 里按 `message.plan` 画）。
 * 于是它跟着消息一起滚走：搭子一边执行一边往后输出，用户想核对"现在做到第几步"
 * 得先往回滚好几屏 —— 而计划的价值恰恰在于**始终可见**。
 *
 * 现在它固定停在输入栏上方：看得见进度、看得见还剩几步，且不占聊天记录的地方。
 *
 * ## 展开态的记忆范围
 *
 * **一次对话 = 一种展开态**。搭子发起新计划时自动展开（产品要求），之后用户
 * 收起就收起 —— 他收起是在说"我知道有它，现在不想看细节"。所以用 `useState`
 * 而不是 localStorage：切到别的对话应该回到默认（展开），而不是继承上一个对话
 * 的偏好。
 */

import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { ChevronRight, ListChecks } from 'lucide-react'

import { PlanCard } from '@/components/chat/PlanCard'
import type { ChatMessage, Plan } from '@/types'

/** 从当前会话的消息里挑出**最新**的那份计划（后发起的覆盖先前的）。 */
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

  /*
    ⚠️ 必须用 `useEffect`，**不能在渲染期间直接 setState**。

    这里踩过一个真实的坑：原先写的是
        if (plan && plan.id !== seenId) { setSeenId(plan.id); setOpen(true) }
    看起来"计划换了就展开"很直白，实际上它**每次渲染都可能重跑** ——
    React 在渲染中 setState 会立刻丢弃本次渲染并重来一次，而这个比较依赖
    `seenId`，用户点收起之后 `open` 变 false → 重渲染 → 条件照样成立
    （`plan.id` 没变但 `seenId` 是上一次设的、本该相等……一旦因为任何原因
    不等，就会再次 setOpen(true)）。表现出来就是**用户收起后它自己又弹开**，
    点不动。
  */
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
      {/*
        收起时**只剩这一行**（产品要求"大概一行字的高度即可"）：标题 + 进度条
        + "3/5"。进度必须留着 —— 收起是为了省地方，不是为了失去"做到哪了"。
      */}
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

        {/* 进度条：收起时它是唯一能看出"快完了没有"的东西 */}
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
        // 展开体**直接复用 `PlanCard`**（`hideHeader` 去掉它自带的标题/进度行，
        // 那是上面那一条的职责）。不另写一份明细渲染 —— 目标、步骤、以及
        // "开始执行 / 改一下 / 不用了"三个按钮都在那里，各写一份必然长歪，
        // 而且会漏掉某一边新加的操作。
        <PlanCard plan={plan} hideHeader />
      ) : null}
    </div>
  )
}
