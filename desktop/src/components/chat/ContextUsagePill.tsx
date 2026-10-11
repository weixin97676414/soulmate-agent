import clsx from 'clsx'
import { useEffect, useRef, useState } from 'react'

import { formatTokens } from '@/lib/format'
import { useAppStore } from '@/stores/appStore'
import { useChatStore } from '@/stores/chatStore'
import type { SessionContext } from '@/types'

/**
 * ⚠️ token 数的格式统一走 `lib/format`（第 93 批收拢）。
 *
 * 这里原先自带**第二份**实现（`1.5M` / `15k`），而用量页在上次已改成中文口径
 * （`150万` / `1.5万`）—— 同一个数在两处显示成两种写法，用户会以为是两个不同的量。
 */

/**
 * 输入区底部的上下文占用胶囊。
 *
 * ## 什么时候刷新
 *
 * **只在"模型回答完"与"切换会话"时拉一次**。上下文用量只在这两个时刻变化，
 * 跟着每个 token 刷新既没有意义（用户在打字时并不关心），又会把本地服务打满。
 *
 * ## 为什么数值来自后端
 *
 * "实际会发给模型的量"要算上系统提示词、已生成的摘要、以及图片占的 token。
 * 前端拿消息的 usage 相加会偏小，而用户据此以为"还很空"，正好错过即将到来的压缩。
 */
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
        // 拿不到就不显示：这只是个提示，不该因为它冒出错误提示
      }
    })()
    return () => {
      cancelled = true
    }
  }, [api, activeSessionId, streaming, messageCount])

  // 点别处 / Esc 收起面板 —— 与 ConfirmModeButton 同一套写法
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

  // 换了会话就把旧数据丢掉，免得短暂显示上一个会话的占用
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
