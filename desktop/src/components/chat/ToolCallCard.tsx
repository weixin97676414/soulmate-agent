import clsx from 'clsx'
import {
  AlertCircle,
  ChevronRight,
  Loader2,
  ShieldX,
  Wrench,
  CheckCircle2,
} from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui'
import { formatClock } from '@/lib/time'
import type { ToolCallState } from '@/types'

const STATUS_META: Record<
  ToolCallState['status'],
  { icon: typeof CheckCircle2; tone: 'brand' | 'success' | 'danger' | 'warning'; label: string }
> = {
  running: { icon: Loader2, tone: 'brand', label: '运行中' },
  ok: { icon: CheckCircle2, tone: 'success', label: '已完成' },
  error: { icon: AlertCircle, tone: 'danger', label: '失败' },
  denied: { icon: ShieldX, tone: 'warning', label: '已拒绝' },
}

function formatDuration(ms?: number): string {
  if (ms === undefined) return ''
  if (ms < 1000) return `${Math.round(ms)} ms`
  return `${(ms / 1000).toFixed(2)} s`
}









const PREVIEW_CHARS = 4000







export function ToolCallCard({ tool }: { tool: ToolCallState }) {
  const [open, setOpen] = useState(false)
  
  const [full, setFull] = useState(false)
  const meta = STATUS_META[tool.status]
  const Icon = meta.icon

  const result = tool.result ?? ''
  const resultTooLong = result.length > PREVIEW_CHARS
  const shownResult = full || !resultTooLong ? result : result.slice(0, PREVIEW_CHARS)
  const paramsText = JSON.stringify(tool.params ?? {}, null, 2)
  const paramsTooLong = paramsText.length > PREVIEW_CHARS
  const shownParams =
    paramsTooLong && !full ? `${paramsText.slice(0, PREVIEW_CHARS)}\n…（参数过长，已折叠）` : paramsText

  return (
    <div
      className={clsx(
        'my-2 overflow-hidden rounded-[10px] border bg-canvas transition-colors',
        tool.status === 'error'
          ? 'border-danger/30'
          : tool.status === 'denied'
            ? 'border-warning/30'
            : 'border-line',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="no-drag flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-hover"
      >
        <ChevronRight
          size={13}
          className={clsx(
            'shrink-0 text-ink-faint transition-transform',
            open && 'rotate-90',
          )}
        />
        <Wrench size={13} className="shrink-0 text-ink-faint" />
        <span className="shrink-0 text-[12.5px] font-medium text-ink">{tool.displayName}</span>
        <code className="shrink-0 rounded-[4px] bg-panel px-1 py-[1px] text-[11px] text-ink-faint">
          {tool.name}
        </code>

        <span className="min-w-0 flex-1" />

        {
}
        {tool.startedAt !== undefined ? (
          <span className="shrink-0 text-[11.5px] text-ink-faint" title={`开始于 ${formatClock(tool.startedAt)}`}>
            {formatClock(tool.startedAt)}
          </span>
        ) : null}
        {tool.durationMs !== undefined ? (
          <span className="shrink-0 text-[11.5px] text-ink-faint">
            {formatDuration(tool.durationMs)}
          </span>
        ) : null}
        <Badge tone={meta.tone} className="shrink-0">
          <Icon
            size={10}
            className={clsx('mr-1', tool.status === 'running' && 'animate-spin')}
          />
          {meta.label}
        </Badge>
      </button>

      {open ? (
        <div className="border-t border-line-soft px-3 py-2.5">
          {tool.description ? (
            <p className="mb-2 text-[12px] leading-relaxed text-ink-soft">{tool.description}</p>
          ) : null}

          <div className="mb-1 text-[11px] font-medium text-ink-faint">调用参数</div>
          <pre className="selectable max-h-[180px] overflow-auto rounded-[8px] border border-line bg-panel p-2 text-[11.5px] leading-relaxed break-all whitespace-pre-wrap text-ink-soft">
            {shownParams}
          </pre>

          {tool.result !== undefined ? (
            <>
              <div className="mt-2.5 mb-1 text-[11px] font-medium text-ink-faint">返回结果</div>
              <pre
                className={clsx(
                  
                  'selectable max-h-[280px] overflow-auto rounded-[8px] border p-2 text-[11.5px] leading-relaxed break-all whitespace-pre-wrap',
                  tool.status === 'error' || tool.status === 'denied'
                    ? 'border-danger/25 bg-danger-soft text-ink-soft'
                    : 'border-line bg-panel text-ink-soft',
                )}
              >
                {shownResult}
              </pre>
              {resultTooLong || paramsTooLong ? (
                <div className="mt-1.5 flex items-center gap-2 text-[11px] text-ink-faint">
                  <span>
                    {resultTooLong
                      ? `结果共 ${result.length.toLocaleString()} 字符`
                      : `参数共 ${paramsText.length.toLocaleString()} 字符`}
                    {result.includes('界面预览已省略') ? '（后端已截断，完整内容在模型那边）' : ''}
                  </span>
                  <button
                    type="button"
                    onClick={() => setFull((value) => !value)}
                    className="rounded-[6px] border border-line px-2 py-0.5 text-ink-soft hover:bg-hover"
                  >
                    {full ? '收起' : '展开全部'}
                  </button>
                </div>
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
