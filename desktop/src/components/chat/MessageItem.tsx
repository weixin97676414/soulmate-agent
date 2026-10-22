import clsx from 'clsx'
import { AlertCircle, Ban, Brain, Check, ChevronRight, Copy } from 'lucide-react'
import { memo, useState } from 'react'

import { Markdown } from '@/components/chat/Markdown'
import { ToolCallCard } from '@/components/chat/ToolCallCard'
import { AssistantAvatar } from '@/components/chat/AssistantFormModal'
import { loadUserProfile } from '@/lib/userProfile'
import { useUserProfileDialogStore } from '@/stores/userProfileDialogStore'
import { formatClock, formatFull } from '@/lib/time'
import { useAssistantStore } from '@/stores/assistantStore'
import type { ChatMessage } from '@/types'







export function ReasoningBlock({ text }: { text: string }) {
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

  
  if (message.role === 'user') {
    
    
    const profile = loadUserProfile()
    const showProfileDialog = useUserProfileDialogStore.getState().show
    return (
      <div className="animate-enter flex items-start justify-end gap-3">
        <div className="flex max-w-[78%] flex-col items-end">
          {profile.nickname || message.createdAt ? (
            <span className="mb-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
              {



}
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
          {

}
          <div className="selectable rounded-[12px] rounded-br-[4px] bg-brand-soft px-3.5 py-2 text-left text-[13.5px] leading-relaxed whitespace-pre-wrap text-ink">
            {message.content}
          </div>
        </div>
        {
}
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

  
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      
    }
  }

  const hasBody = message.content.trim().length > 0
  const hasTools = message.toolCalls.length > 0

  









  const visible =
    hasBody ||
    Boolean(message.plan) ||
    Boolean(message.reasoning) ||
    hasTools ||
    Boolean(message.error) ||
    message.status === 'streaming' ||
    message.status === 'cancelled'
  if (!visible) return null

  
  
  
  const cacheRate =
    typeof message.usage?.cache_hit_rate === 'number' &&
    typeof message.usage?.cached_tokens === 'number'
      ? message.usage.cache_hit_rate
      : null

  









  const assistantId = message.assistantId
  const assistant = useAssistantStore((state) =>
    assistantId
      ? state.assistants.find((item) => item.id === assistantId)
      : state.assistants.find((item) => item.id === state.activeId),
  )
  const assistantLabel = assistant?.nickname || assistant?.name

  return (
    <div className="animate-enter flex gap-3">
      {assistant ? (
        <AssistantAvatar profile={assistant} size={26} className="mt-0.5" />
      ) : (
        




        <div className="mt-0.5 size-[26px] shrink-0 rounded-full bg-hover" aria-hidden="true" />
      )}

      <div className="group min-w-0 flex-1">
        {assistantLabel || message.createdAt ? (
          <div className="mb-0.5 flex items-center gap-2 text-[11px] text-ink-faint">
            {assistantLabel ? <span>{assistantLabel}</span> : null}
            {
}
            {message.createdAt ? (
              <span title={formatFull(message.createdAt)}>
                {formatClock(message.createdAt)}
              </span>
            ) : null}
          </div>
        ) : null}
        {







}

        {message.reasoning ? <ReasoningBlock text={message.reasoning} /> : null}

        {














}
        {message.toolCalls.map((tool) => (
          <ToolCallCard key={tool.id} tool={tool} />
        ))}

        {hasBody ? (
          <Markdown content={message.content} />
        ) : message.status === 'streaming' && message.plan?.state !== 'awaiting' ? (
          
          
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
              {




}
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
