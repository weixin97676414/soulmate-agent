import clsx from 'clsx'
import { AlertCircle, Ban, Brain, Check, ChevronRight, Copy } from 'lucide-react'
import { memo, useState } from 'react'

import { Markdown } from '@/components/chat/Markdown'
import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { loadUserProfile } from '@/lib/userProfile'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { formatClock, formatFull } from '@/lib/time'
import { useAssistantStore } from '@/stores/assistantStore'
import type { ChatMessage } from '@/types'

function ReasoningBlock({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="mb-2 overflow-hidden rounded-[10px] border border-line bg-panel">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="no-drag flex w-full items-center gap-1.5 px-3 py-1.5 text-left text-[12px] text-ink-soft hover:text-ink"
      >
        <Brain size={12} />
        深度思考
        <ChevronRight size={12} className={clsx('transition-transform', open && 'rotate-90')} />
      </button>
      {open ? (
        <div className="border-t border-line-soft px-3 py-2 text-[12px] leading-relaxed whitespace-pre-wrap text-ink-soft">
          {text}
        </div>
      ) : null}
    </div>
  )
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-1 text-ink-faint">
      <span className="caret" />
    </div>
  )
}

export const MessageItem = memo(function MessageItem({ message }: { message: ChatMessage }) {
  const [copied, setCopied] = useState(false)

  // ---- 用户消息：右侧浅色气泡 + 用户头像/昵称 ------------------------ //
  if (message.role === 'user') {
    // 不走 zustand 订阅：资料是纯本机低频数据，组件挂载时读一次足够，
    // 变化由页面刷新/重挂载自然带上
    const profile = loadUserProfile()
    const showProfileDialog = useUserProfileDialogStore.getState().show
    return (
      <div className="animate-enter flex items-start justify-end gap-3">
        <div className="flex max-w-[78%] flex-col items-end">
          {profile.nickname || message.createdAt ? (
            <span className="mb-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
              {/*
                ⚠️ 昵称可点（产品要求："在单聊/群聊当中点击自己的
                头像/昵称进行修改"）。做成 `<button>` 而不是给 span 挂 onClick：
                只有 button 天然带键盘焦点与回车触发。
              */}
              {profile.nickname ? (
                <button
                  type="button"
                  onClick={showProfileDialog}
                  title="修改我的资料"
                  className="rounded-[4px] transition-colors hover:text-ink"
                >
                  {profile.nickname}
                </button>
              ) : null}
              {message.createdAt ? (
                <span title={formatFull(message.createdAt)}>
                  {formatClock(message.createdAt)}
                </span>
              ) : null}
            </span>
          ) : null}
          {/* `text-left` 是**显式**钉住的：这一层是 flex 容器（items-end 让气泡
              贴右），气泡整体的位置与它内部文字的对齐是两件事 —— 少一次钉住，
              以后有人往这层加 text-align 就会让用户的多行消息变成右边参差不齐。 */}
          <div className="selectable rounded-[12px] rounded-br-[4px] bg-brand-soft px-3.5 py-2 text-left text-[13.5px] leading-relaxed whitespace-pre-wrap text-ink">
            {message.content}
          </div>
        </div>
        {/* 头像可点：打开「我的资料」弹窗（与搭子头像点开大图区分开 ——
            用户对自己的头像是"想改"，对搭子的头像是"想看清楚"） */}
        <button
          type="button"
          onClick={showProfileDialog}
          title="修改我的资料"
          aria-label="修改我的资料"
          className="mt-0.5 shrink-0 cursor-pointer overflow-hidden"
          style={{ width: 26, height: 26, borderRadius: Math.round(26 * (6 / 22)) }}
        >
          {profile.avatar ? (
            <img
              src={profile.avatar}
              alt="我"
              width={26}
              height={26}
              draggable={false}
              className="h-full w-full object-cover select-none"
            />
          ) : (
            <span className="flex h-full w-full items-center justify-center bg-brand-soft text-[11px] text-brand">
              我
            </span>
          )}
        </button>
      </div>
    )
  }

  // ---- 助手消息：全宽 Markdown ------------------------------------ //
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      // 忽略
    }
  }

  const hasBody = message.content.trim().length > 0
  const hasTools = message.toolCalls.length > 0

  /*
    可见性闸门（反馈：对话里出现**空白行**）。

    一条消息可能**什么都没得显示**：这一轮只调了工具、而工具卡片本身又因
    "内部零件不露脸"渲染成空，或者流式开始时的空壳助手消息。此时仍然渲染
    外层骨架，用户看到的就是一行什么都不含的空白 —— 看起来像界面坏了。

    判据要写**全**（正文 / 计划 / 思考 / 工具 / 错误 / 中断 / 正在流式），
    宁可多显示一个空壳，也不要因为有新的消息形态而把正常内容吞掉。
  */
  const visible =
    hasBody ||
    Boolean(message.plan) ||
    Boolean(message.reasoning) ||
    hasTools ||
    Boolean(message.error) ||
    message.status === 'streaming' ||
    message.status === 'cancelled'
  if (!visible) return null

  // 只在厂商确实返回了缓存信息时才显示命中率。
  // 没有这个字段说明该端点不支持前缀缓存，显示"缓存 0%"会让用户
  // 以为是自己配置错了，而去改一堆无关的设置。
  const cacheRate =
    typeof message.usage?.cache_hit_rate === 'number' &&
    typeof message.usage?.cached_tokens === 'number'
      ? message.usage.cache_hit_rate
      : null

  // 助手消息的头像 = **当前助手的头像**（不是应用 logo），昵称用助手昵称。
  const assistant = useAssistantStore((state) =>
    state.assistants.find((item) => item.id === state.activeId),
  )
  const assistantLabel = assistant?.nickname || assistant?.name

  return (
    <div className="animate-enter flex gap-3">
      {assistant ? (
        <AssistantAvatar profile={assistant} size={26} className="mt-0.5" />
      ) : null}

      <div className="group min-w-0 flex-1">
        {assistantLabel || message.createdAt ? (
          <div className="mb-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
            {assistantLabel ? <span>{assistantLabel}</span> : null}
            {/* 时间戳：记忆要有时间维度，界面上也得看得见。
                悬停给完整时刻；老消息（时间不可信）什么都不显示。 */}
            {message.createdAt ? (
              <span title={formatFull(message.createdAt)}>
                {formatClock(message.createdAt)}
              </span>
            ) : null}
          </div>
        ) : null}
        {/*
          ⚠️ 这里原本在消息内部渲染 `<PlanCard>`。按产品要求，
          计划挪去了**对话栏与输入栏之间的「任务执行计划」条**（`PlanBar`）——
          它跟着消息滚走之后，"现在做到第几步"就得往回滚几屏才能看到，
          而计划的价值恰恰在于始终可见。

          `message.plan` 字段本身保留（不删）：`PlanBar` 正是靠消息上的这个字段
          找出"当前这份计划"的。
        */}

        {message.reasoning ? <ReasoningBlock text={message.reasoning} /> : null}

        {/*
          ⚠️ 这里原本把每一次工具调用都渲染成一张 `ToolCallCard`（参数、结果、
          耗时全摊开）。产品要求**对话栏不再展示工具调用记录**。

          理由成立：这些卡片属于"任务过程"，而它们占的高度往往超过回答本身 ——
          一次搜索 + 一次读写就有五六张卡，用户得不停往下滑才能看到搭子说了什么。
          过程信息现在有更好的去处：**链路与产物**抽屉（它本来就是完整时间线），
          而且搭子首次调工具时会自动展开（见 chatStore）。

          注意这里只删了**展示**，`message.toolCalls` 仍然照常累积 ——
          Trace 面板、上下文用量、审计都靠它。
        */}

        {hasBody ? (
          <Markdown content={message.content} />
        ) : message.status === 'streaming' && message.plan?.state !== 'awaiting' ? (
          // 等用户确认计划时不画光标：那一刻模型并没有在生成，
          // 一个闪动的光标会让人以为"它在写"，而实际上它在等**你**做决定
          <TypingIndicator />
        ) : null}

        {message.error ? (
          <div className="mt-2 flex items-start gap-2 rounded-[10px] border border-danger/30 bg-danger-soft px-3 py-2">
            <AlertCircle size={14} className="mt-0.5 shrink-0 text-danger" />
            <span className="selectable text-[12.5px] leading-relaxed text-ink-soft">
              {message.error}
            </span>
          </div>
        ) : null}

        {message.status === 'cancelled' ? (
          <div className="mt-2 flex items-center gap-1.5 text-[12px] text-ink-faint">
            <Ban size={12} />
            已中断生成
          </div>
        ) : null}

        <div className="mt-1 flex items-center gap-2">
          {message.usage && message.status !== 'streaming' ? (
            <span className="flex items-center gap-2 text-[11px] text-ink-faint">
              <span>
                {message.iterations ? `${message.iterations} 轮 · ` : ''}
                {message.usage.total_tokens} tokens
              </span>
              {/*
                缓存命中率是最值得给用户看的一个指标：命中部分的输入单价
                可能只有未命中的 1/10，它直接决定了同样一段上下文要花多少钱。
                system 提示词里那个按分钟变化的时间戳就是在无声地把它变成 0，
                所以这里必须显式呈现，用户才有机会发现"缓存没生效"。
              */}
              {cacheRate !== null ? (
                <span
                  title={`输入 ${message.usage.prompt_tokens} tokens，其中 ${message.usage.cached_tokens} 命中缓存`}
                  className={clsx(
                    'rounded-[4px] px-1 py-px',
                    cacheRate >= 0.5
                      ? 'bg-success-soft text-success'
                      : cacheRate > 0
                        ? 'bg-warning-soft text-warning'
                        : 'bg-hover text-ink-faint',
                  )}
                >
                  缓存 {Math.round(cacheRate * 100)}%
                </span>
              ) : null}
            </span>
          ) : null}

          {hasBody && message.status !== 'streaming' ? (
            <button
              type="button"
              onClick={() => void copy()}
              className="no-drag flex items-center gap-1 rounded-[6px] px-1.5 py-0.5 text-[11px] text-ink-faint opacity-0 transition-opacity group-hover:opacity-100 hover:bg-hover hover:text-ink"
            >
              {copied ? <Check size={11} /> : <Copy size={11} />}
              {copied ? '已复制' : '复制'}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  )
})
