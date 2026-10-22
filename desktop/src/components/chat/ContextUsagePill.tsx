import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'

import { formatTokens } from '@/lib/format'
import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'
import type { SessionContext } from '@/types'





















export function ContextUsagePill() {
  const api = useAppStore((state) => state.api)
  const activeSessionId = useChatStore((state) => state.activeSessionId)
  const streaming = useChatStore((state) => state.streaming)
  const messageCount = useChatStore((state) => state.messages.length)

  const [open, setOpen] = useState(false)
  const [usage, setUsage] = useState<SessionContext | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!api || !activeSessionId || streaming) return
    let cancelled = false
    void (async () => {
      try {
        const next = await api.getSessionContext(activeSessionId)
        if (!cancelled) setUsage(next)
      } catch {
        
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, activeSessionId, streaming, messageCount])

  
  useEffect(() => {
    if (!open) return
    const onDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  
  useEffect(() => {
    setUsage(null)
    setOpen(false)
  }, [activeSessionId])

  if (!activeSessionId || !usage || usage.limit_tokens <= 0) return null

  const percent = Math.min(Math.round(usage.ratio * 100), 999)
  const near = usage.ratio >= usage.compress_threshold
  const over = usage.ratio >= 0.9
  const tone = over ? 'text-danger' : near ? 'text-warning' : 'text-ink-faint'
  const barTone = over ? 'bg-danger' : near ? 'bg-warning' : 'bg-brand'

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        title="上下文使用情况"
        className={clsx(
          'no-drag flex items-center gap-1.5 rounded-[6px] px-1.5 py-0.5 text-[11px] hover:bg-hover',
          tone,
        )}
      >
        <span className="h-[4px] w-[36px] overflow-hidden rounded-full bg-line-soft">
          <span
            className={clsx('block h-full rounded-full', barTone)}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </span>
        上下文 {percent}%
      </button>

      {open ? (
        <div className="absolute right-0 bottom-full z-30 mb-2 w-[300px] overflow-hidden rounded-[10px] border border-line bg-canvas shadow-[0_10px_30px_rgba(0,0,0,0.16)]">
          <div className="border-b border-line px-3 py-2 text-[12.5px] font-medium text-ink">
            上下文使用情况
          </div>
          <div className="flex flex-col gap-1.5 px-3 py-2.5 text-[12px] text-ink-soft">
            <div className="flex justify-between">
              <span>已用</span>
              <span className="text-ink">{formatTokens(usage.used_tokens)} tokens</span>
            </div>
            <div className="flex justify-between">
              <span>模型上限</span>
              <span className="text-ink">{formatTokens(usage.limit_tokens)} tokens</span>
            </div>
            <div className="flex justify-between">
              <span>还能再放</span>
              <span className="text-ink">{formatTokens(usage.remaining_tokens)} tokens</span>
            </div>
            <div className="flex justify-between">
              <span>自动压缩</span>
              <span className="text-ink">超过 {Math.round(usage.compress_threshold * 100)}% 时</span>
            </div>
          </div>
          <div className="border-t border-line px-3 py-2 text-[11px] leading-relaxed text-ink-faint">
            {usage.summary_chars > 0
              ? `早期对话已压缩成 ${usage.summary_chars} 字的摘要，完整聊天记录仍然保留。`
              : '接近上限时，更早的对话会被自动压缩成摘要，聊天记录本身不会丢。'}
          </div>
        </div>
      ) : null}
    </div>
  )
}
